"""Product-of-experts VAE (Wu & Goodman). JAX/Equinox when available."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from transforms import product_of_experts, sample_view_mask

try:
    import equinox as eqx
    import jax
    import jax.numpy as jnp
    import optax

    HAS_JAX = True
except Exception:  # pragma: no cover - optional at unit-test time
    HAS_JAX = False
    eqx = None
    jax = None
    jnp = None
    optax = None


def gaussian_nll(x: np.ndarray, mu: np.ndarray, logvar: np.ndarray) -> float:
    var = np.exp(logvar)
    return float(0.5 * np.mean((x - mu) ** 2 / var + logvar + np.log(2 * np.pi)))


def beta_nll(x: np.ndarray, alpha: np.ndarray, beta: np.ndarray) -> float:
    x = np.clip(x, 1e-4, 1 - 1e-4)
    from scipy.special import betaln, gamma  # noqa: F401

    from scipy.stats import beta as beta_dist

    return float(-np.mean(beta_dist.logpdf(x, np.clip(alpha, 1e-3, None), np.clip(beta, 1e-3, None))))


@dataclass
class NumpyPoEFit:
    """Linear-encoder fallback used when JAX is not installed."""

    means: list[np.ndarray]
    logvars: list[np.ndarray]
    latent_dim: int

    def encode(self, views: list[np.ndarray | None]) -> tuple[np.ndarray, np.ndarray]:
        mus, logvars, mask = [], [], []
        batch = next(v.shape[0] for v in views if v is not None)
        for i, view in enumerate(views):
            if view is None:
                mus.append(np.zeros((batch, self.latent_dim)))
                logvars.append(np.zeros((batch, self.latent_dim)))
                mask.append(np.zeros((batch, 1)))
            else:
                z = view @ self.means[i]
                mus.append(z)
                logvars.append(np.broadcast_to(self.logvars[i], z.shape).copy())
                mask.append(np.ones((batch, 1)))
        return product_of_experts(
            np.stack(mus, 0),
            np.stack(logvars, 0),
            np.stack(mask, 0),
        )


def fit_linear_poe(
    views: list[np.ndarray],
    latent_dim: int = 16,
    rng: np.random.Generator | None = None,
) -> NumpyPoEFit:
    rng = rng or np.random.default_rng(0)
    means, logvars = [], []
    for view in views:
        # PCA loadings as a cheap unimodal encoder.
        view_c = view - view.mean(0, keepdims=True)
        u, s, vt = np.linalg.svd(view_c, full_matrices=False)
        k = min(latent_dim, vt.shape[0])
        W = vt[:k].T
        if k < latent_dim:
            pad = rng.normal(scale=0.01, size=(view.shape[1], latent_dim - k))
            W = np.concatenate([W, pad], axis=1)
        means.append(W)
        logvars.append(np.full((latent_dim,), -1.0))
    return NumpyPoEFit(means=means, logvars=logvars, latent_dim=latent_dim)


if HAS_JAX:

    class MLP(eqx.Module):
        layers: tuple

        def __init__(self, sizes, key):
            keys = jax.random.split(key, len(sizes) - 1)
            self.layers = tuple(
                eqx.nn.Linear(a, b, key=k) for (a, b), k in zip(zip(sizes[:-1], sizes[1:]), keys)
            )

        def __call__(self, x):
            for i, layer in enumerate(self.layers):
                x = layer(x)
                if i < len(self.layers) - 1:
                    x = jax.nn.silu(x)
            return x

    class PoEVAE(eqx.Module):
        encoders: tuple
        decoders: tuple
        latent_dim: int

        def __init__(self, input_dims: list[int], latent_dim: int, key, hidden: int = 64):
            keys = jax.random.split(key, 2 * len(input_dims))
            self.encoders = tuple(
                MLP([d, hidden, hidden, 2 * latent_dim], keys[i]) for i, d in enumerate(input_dims)
            )
            self.decoders = tuple(
                MLP([latent_dim, hidden, hidden, d], keys[len(input_dims) + i])
                for i, d in enumerate(input_dims)
            )
            self.latent_dim = latent_dim

        def encode_view(self, view_idx, x):
            h = jax.vmap(self.encoders[view_idx])(x)
            mu, logvar = jnp.split(h, 2, axis=-1)
            return mu, logvar

        def decode_view(self, view_idx, z):
            return jax.vmap(self.decoders[view_idx])(z)

    def train_poe_vae(
        views: list[np.ndarray],
        latent_dim: int = 16,
        steps: int = 400,
        batch_size: int = 64,
        seed: int = 0,
    ):
        input_dims = [v.shape[1] for v in views]
        key = jax.random.PRNGKey(seed)
        model = PoEVAE(input_dims, latent_dim, key)
        opt = optax.adam(1e-3)
        opt_state = opt.init(eqx.filter(model, eqx.is_inexact_array))
        data = [jnp.asarray(v, dtype=jnp.float32) for v in views]
        n = data[0].shape[0]

        @eqx.filter_jit
        def step(model, opt_state, key, idx):
            batch = [d[idx] for d in data]
            n_views = len(batch)

            def loss_fn(model):
                mus, logvars = [], []
                for i, x in enumerate(batch):
                    mu, lv = model.encode_view(i, x)
                    mus.append(mu)
                    logvars.append(lv)
                mus = jnp.stack(mus)
                logvars = jnp.stack(logvars)
                mask_key, eps_key = jax.random.split(key)
                full = jnp.ones((n_views, idx.shape[0], 1))
                rand = jax.random.bernoulli(mask_key, 0.5, (n_views, idx.shape[0], 1)).astype(jnp.float32)
                rand = jnp.where(rand.sum(0, keepdims=True) == 0, full, rand)
                mask = jnp.concatenate([full, rand], axis=1)
                mus2 = jnp.concatenate([mus, mus], axis=1)
                lv2 = jnp.concatenate([logvars, logvars], axis=1)
                prec = jnp.exp(-lv2) * mask
                prior = jnp.ones_like(prec[0])
                total = prec.sum(0) + prior
                mu_j = (mus2 * prec).sum(0) / total
                lv_j = -jnp.log(total)
                eps = jax.random.normal(eps_key, mu_j.shape)
                z = mu_j + eps * jnp.exp(0.5 * lv_j)
                rec = 0.0
                bsz = idx.shape[0]
                for i, x in enumerate(batch):
                    x2 = jnp.concatenate([x, x], axis=0)
                    hat = model.decode_view(i, z)
                    rec = rec + jnp.mean((hat - x2) ** 2)
                kl = 0.5 * jnp.mean(jnp.exp(lv_j) + mu_j ** 2 - 1.0 - lv_j)
                return rec + 0.1 * kl

            loss, grads = eqx.filter_value_and_grad(loss_fn)(model)
            updates, opt_state = opt.update(grads, opt_state, eqx.filter(model, eqx.is_inexact_array))
            model = eqx.apply_updates(model, updates)
            return model, opt_state, loss

        losses = []
        for s in range(steps):
            key, k1, k2 = jax.random.split(key, 3)
            idx = jax.random.choice(k1, n, (min(batch_size, n),), replace=False)
            model, opt_state, loss = step(model, opt_state, k2, idx)
            losses.append(float(loss))
        return model, losses
else:  # pragma: no cover

    def train_poe_vae(*args, **kwargs):
        raise ImportError("JAX/Equinox not installed; use fit_linear_poe or MOFA+")
