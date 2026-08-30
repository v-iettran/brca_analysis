# Putting the panel online

This walks through publishing the breast-cancer research panel so anyone with the
link can use it. It assumes no prior deployment experience. Every command is
meant to be copied and pasted exactly.

Set aside about 40 minutes the first time. Most of it is waiting.

---

## What you are actually deploying

The panel is **two programs that talk to each other**:

| | What it is | What it does |
|---|---|---|
| **web** | The Next.js site | Everything you see: the panels, the charts, the copilot window |
| **api** | The FastAPI server | Holds the data, runs each analysis, answers the copilot |

They must both be online. This is the reason Vercel alone will not work: Vercel is
built for the first kind and not the second. The API keeps a database, serves
39 MB of pre-computed results, and takes about ten seconds per analysis.

**Render** runs both, and `application/render.yaml` describes them. Render reads
that file and creates everything for you.

It is configured for Render's **free tier**, so it needs no card. Three things
follow from that, and they are worth knowing before you send anyone the link:

- **The API has its own public address.** Render's free tier only offers public
  web services. The API is still locked to your site by an allowlist, rate
  limited to 30 requests a minute, has uploads disabled and its documentation
  page turned off — but the address exists.
- **Runs disappear when a service restarts.** There is no permanent storage on
  the free tier, so the database sits in temporary space. Runs and copilot
  conversations are deleted after 24 hours in any case; the practical effect is
  that a restart mid-session loses the conversation.
- **The first visit after a quiet spell is slow.** A free service goes to sleep
  after about 15 minutes idle and takes roughly a minute to wake up. If you are
  sending the link to someone specific, open it yourself a minute beforehand.

Paying removes all three — see the end of this guide.

---

## Before you start

You need:

- A **GitHub account**, with the `brca_analysis` repository already on it.
- A **Render account** — sign up at render.com with your GitHub login. No card
  is needed for the setup as configured.

You do **not** need Docker installed. Render builds the images on its side.

---

## Step 1 — get the current work into the repository

**This step is easy to miss and nothing else will work without it.**

The folder you have been working in (`final-project`) and the folder that is
connected to GitHub (`brca_analysis`) are two separate copies. The GitHub copy is
still frozen at 25 August and contains none of the recent work.

Copy the work across:

```bash
cd ~/Desktop/UCD/Class/Summer/AI-for-PM/final-project
bash sync_to_repo.sh
```

That only copies files. Now look at what changed, commit it, and publish it:

```bash
cd ../brca_analysis
git status
git add -A
git commit -m "v3.2: clinical redesign, evidence tiers, grounded copilot"
git push
```

`git push` is the moment your code becomes public on GitHub. Everything before it
is reversible.

> **Check before you push.** The payloads contain real TCGA patient identifiers
> with age, stage and histology. TCGA's open tier is meant to be redistributable,
> so this is very probably fine — but it will be published under your name, so
> confirm it rather than take my word for it.

---

## Step 2 — check your address

Render builds your web address from the **web service's name**, so the name and
the two allowlists have to agree. Open `application/render.yaml`. The name is
near the top:

```yaml
  - type: web
    name: brca-research-demo
```

and near the bottom, two lines repeat it:

```yaml
      - key: CORS_ORIGINS
        value: '["https://brca-research-demo.onrender.com"]'
      - key: TRUSTED_HOSTS
        value: '["brca-research-demo.onrender.com","brca-research-demo-api.onrender.com","localhost"]'
```

As shipped these are consistent: the service is `brca-research-demo`, so the site
will be at `https://brca-research-demo.onrender.com`. **If you change the name,
change all three places.**

Those two lists are a safety catch: the API refuses requests that did not come
from your own site. **If they do not match the real address exactly — including
`https://` — the site will load but every panel will stay empty.** That is the
single most common way this goes wrong.

The API service is `brca-research-demo-api`, and it has its own address at
`https://brca-research-demo-api.onrender.com`. If you rename it, change
`INTERNAL_API_URL` and `TRUSTED_HOSTS` to match as well — four places in total
across the two services.

Commit and push the change:

```bash
git add application/render.yaml
git commit -m "Set the public hostname"
git push
```

---

## Step 3 — create the services on Render

1. Go to **dashboard.render.com** and click **New → Blueprint**.
2. Choose the `brca_analysis` repository.
3. Render finds `application/render.yaml` and shows you two services to create:
   `brca-research-demo` and `brca-research-demo-api`. Confirm.
4. It asks about the values marked `sync: false` — `HOSTED_LLM_API_KEY`,
   `HOSTED_LLM_BASE_URL`, `PAPERCLIP_API_KEY`. **You can leave all three empty**
   (see Step 4).
5. Click create, then wait. The first build takes roughly 10–15 minutes, mostly
   installing Python packages. Later ones are quicker.

When both services show **Live**, open `https://brca-research-demo.onrender.com`.

---

## Step 4 — decide about the copilot

The copilot works in two modes, and this is a real choice rather than a detail.

**Without a key (nothing to do).** It answers from a deterministic summary
generated directly from the run. Those answers are correct by construction, and
the interface labels each one `deterministic summary`. Nothing looks broken.

**With a hosted key.** It writes in full sentences and can connect panels into an
argument. Set `HOSTED_LLM_API_KEY` and `HOSTED_LLM_BASE_URL` in the Render
dashboard under the API service's Environment tab.

Two things to weigh. It costs money per question, and strangers will be asking
the questions. And the local model you have been using — `qwen3:8b` through
Ollama — **cannot** be deployed here: it needs a graphics card and far more
memory than these plans have.

For a course submission, my suggestion is to publish without a key and
demonstrate the local model live on your own machine. The safety machinery is the
interesting part, and it behaves identically either way.

Paperclip literature search **does** work online, and needs only
`PAPERCLIP_API_KEY` set on the API service. The SDK is installed during the build by
`scripts/install_paperclip.py`, which works around a vendor packaging fault described
below. Without a key the literature sections state that plainly instead of showing an
empty list.

Two things to weigh, since the searches now run on behalf of whoever visits. Each
nominated drug or gene triggers up to four queries against the vendor, so the key is
being spent by strangers; individual searches are capped at 8 seconds so a slow vendor
cannot stall an analysis. If that worries you, leave the key unset — the panels then
say so honestly, and nothing else changes.

---

## Operating it

**Watching it.** Each service has a **Logs** tab in the Render dashboard. That is
where errors appear. `https://brca-research-demo.onrender.com` loading is the
quickest sign it is alive.

**Publishing a change.** Push to GitHub and Render rebuilds automatically:

```bash
cd ~/Desktop/UCD/Class/Summer/AI-for-PM/final-project
bash sync_to_repo.sh
cd ../brca_analysis && git add -A && git commit -m "what changed" && git push
```

**After you change the pipeline.** If you re-run anything under `v3/scripts/`,
the payloads under `application/apps/api/app/data/v3/` change and must be synced
and pushed like anything else. The site reads them fresh on each request, so no
extra step is needed beyond the push.

**What visitors can and cannot do.** Uploads are off, so nobody can submit their
own patient data. Rate limits allow 30 requests a minute and 12 analyses an hour
per visitor. Runs and copilot conversations are deleted after 24 hours. The API
documentation page is disabled.

**If the site loads but the panels are empty.** Almost always the hostname in
`CORS_ORIGINS` does not match the real address. Compare them character by
character, fix `render.yaml`, push.

**If the first visit is slow, or a panel reports a 502.** The service was asleep.
Free instances stop after about 15 minutes idle, and the API takes roughly a
minute to wake — long enough that the proxy in front of it gives up and returns a
502 in the meantime.

The page now handles this: reads are retried with a widening delay for about
fifty seconds, and while that happens it says *"Starting the analysis server…"*
rather than showing an error. Writes are never retried, so a cold start cannot
start the same analysis twice.

That covers a normal wake. It does not make it fast. Opening the link yourself a
minute before showing it to anyone is still the reliable move, and upgrading
(below) removes the sleep entirely.

**If a conversation disappears.** The service restarted. Free instances have no
permanent storage; the upgrade below fixes it.

**Taking it down.** Suspend or delete both services from the Render dashboard.
The GitHub repository stays as it is.

---

## Paying for a faster setup

If cold starts or vanishing runs become annoying — around a submission deadline,
say — three edits to `application/render.yaml` upgrade it. Roughly $14 a month,
and you can suspend the services when you are done.

1. Change both `plan: free` lines to `plan: starter`. No more sleeping.
2. Give the API permanent storage by adding this under the API service, and
   changing `COPILOT_DB_PATH` from `/tmp/copilot.db` to `/var/data/copilot.db`:

   ```yaml
       disk:
         name: brca-research-demo-state
         mountPath: /var/data
         sizeGB: 1
   ```

3. Optionally make the API private again: change its `type: web` to
   `type: pserv`, **delete its `healthCheckPath` line**, and set
   `INTERNAL_API_URL` to `http://brca-research-demo-api:8000`. Then the API has
   no public address at all.

Two mistakes to avoid while editing:

- **A private service cannot have a `healthCheckPath`.** Render rejects the whole
  blueprint with *"pserv service type cannot have a health check path"*.
- **Keep the web service name and the allowlists in step.** Render builds the
  hostname from the name, and a mismatch gives you a site that loads with every
  panel empty.

## Three failures, all fixed

All three are recorded here because the causes are easy to recreate.

### 1. "/outputs: not found"

`outputs/` is listed in `.gitignore`, so it is not in the repository Render clones,
so `COPY outputs /app/outputs` had nothing to copy and Docker stopped. The line is
gone. Nothing needed it: the panel serves `app/apps/api/app/data/v3`, and the
compound registry was never generated, so the code already returns an empty result
when it is absent.

The general rule, if a build ever stops on a `COPY`: check the file is actually
committed, not just present on your machine. `git ls-files <path>` prints nothing
if it is not.

### 2. "paperclip.whl is not a valid wheel filename"

`requirements.txt` asks pip to install the Paperclip SDK straight from a URL:

```
gxl-paperclip @ https://paperclip.gxl.ai/paperclip.whl
```

pip refuses. A wheel's filename is not decorative — it is how pip reads the package
name, version and which Python it is for, so it must look like
`gxl_paperclip-1.0.0-py3-none-any.whl`. A bare `paperclip.whl` tells pip nothing, so
it stops, and one unusable line took the whole image down with it.

The image now installs `requirements-public.txt` instead: the same runtime packages,
minus Paperclip and minus pytest, which a running server has no use for.
`requirements.txt` is unchanged, so your local setup still installs everything as
before.

Paperclip is then installed a step later by `scripts/install_paperclip.py`, because
the wheel itself is perfectly good — only its name is wrong. The script downloads it,
reads the package name and version out of the metadata already inside the file, and
writes it back out as `gxl_paperclip-0.7.38-py3-none-any.whl`, which pip accepts.
Nothing is patched or repackaged; it is pure bookkeeping.

That step never fails the build. If the vendor is unreachable the image is built
without the SDK, the literature panel reports it as unavailable, and the rest of the
site is unaffected — losing one panel beats losing the whole deployment.

---

### 3. The site loads, then every panel errors with a 404

The symptom: the page appears, then `Error: API 404 /patients/demo` with a lump of
HTML attached. That HTML is Next.js's own "page not found" page, which is the tell —
the request never left the web service to reach the API at all.

The browser is told to call `/api/...`, and `next.config.ts` is supposed to forward
`/api/:path*` to the API. The forwarding rule was missing.

**Why, and it is worth understanding, because it is counter-intuitive:** Next.js
works out its rewrite rules while it is being *built*, and writes the answer into
`.next/routes-manifest.json`. They are fixed from that moment. The rule is built from
`INTERNAL_API_URL` — but Docker only hands a build the variables that the Dockerfile
explicitly names with `ARG`, and the web Dockerfile named the two `NEXT_PUBLIC_` ones
and not this one. So during the build it was empty, the rule list came out empty, and
that emptiness was sealed into the image. Setting the variable on the service
afterwards changes nothing, because by then the decision has been made.

Two changes. The Dockerfile now declares `ARG INTERNAL_API_URL`. And `next.config.ts`
now refuses to build at all if the browser is being pointed at `/api` while no
forwarding rule can be created — the exact combination that produces a site that
loads and then fails on every request. A build that is going to be broken now stops,
loudly, instead of succeeding and disappointing you later.

One consequence worth knowing: **the API's address is now fixed into the web image at
build time.** If you rename the API service, the web service must be rebuilt, not just
reconfigured. Pushing to GitHub does that anyway.

## What has and has not been checked

Docker is not installed here, so the images have never been built. What I did
instead was run the API with exactly the environment the container sets, against
an empty `outputs/` tree — the state inside the image. In that state:

- the app starts, and the database schema is created on startup;
- `/health` returns 200 to Render's health checker, so the service will go Live;
- all three demo patients run to completion and return their `v3_cohort` and
  `v3_patient` panels;
- the copilot answers in deterministic mode;
- a request from the site's own address is allowed and one from any other address
  is refused, which is the protection standing in for a private API;
- with the Paperclip SDK and the test packages made unavailable, every module still
  imports and the literature panel returns a plain explanation instead of an error;
- the renamed Paperclip wheel installs cleanly into a fresh environment, pulling its
  four dependencies, and exposes the `from_env` and `search` calls the adapter uses.
  All four have Linux wheels for Python 3.12, so no compiler is needed. With a key
  present the adapter builds a real client; with none it returns nothing and the panel
  explains why.

Cold starts are covered by tests rather than by hope: a sleeping upstream that
answers 502 three times and then succeeds, a dropped connection, a 404 (not
retried — that is an answer, not a cold start), a POST (never retried), and the
case where the retries run out, which must not put a page of HTML into the error
message the way the first report did.

The web service was checked differently, because that failure was a build-time one: I
built it locally both ways. Without `INTERNAL_API_URL` the build now stops with the
error above; with it, the forwarding rule appears in `routes-manifest.json`, and the
built server really does forward `/api/patients/demo` to the live API and return the
three demo patients.

`/health` reports `"status": "degraded"`. That is expected and harmless — it refers
to the v1 demo bundle and compound registry, which this panel does not use. The
status code is 200 either way, which is the only thing Render looks at.

**One thing to watch: memory.** A free instance has 512 MB. The API sits at about
250 MB idle, and each analysis reads and parses the two payload files —
`cohort_payload.json` and `demo_payloads_v3.json`, 38 MB of JSON — which costs a
further 135 MB while it runs. One visitor at a time fits. Two analyses starting at
the same moment may not, and Render kills a service that runs out of memory and
restarts it.

If that turns out to happen, the fix is to keep the parsed payloads in memory
between requests instead of re-reading them, keyed on the files' modification time
so a redeploy still picks up new data. That is a deliberate change to how freshly
the panel reads from disk, which is the thing that caused stale results earlier, so
it is worth making on purpose rather than pre-emptively. Upgrading to `starter`
(2 GB) also removes the problem.
