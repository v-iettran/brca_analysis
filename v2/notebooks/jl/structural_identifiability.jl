#!/usr/bin/env julia
# Structural identifiability for the 20-node signed ODE (NB09).
# Usage:
#   julia --project=v2/env/julia structural_identifiability.jl topology.json report.json
#
# Uses StructuralIdentifiability.jl
#   https://github.com/SciML/StructuralIdentifiability.jl
# on a linear signed relaxation of the HillCube graph: n is fixed,
# k and tau are candidates, readouts are E2F1 / MKI67 / CDKN1A.

if length(ARGS) < 2
    println("usage: julia structural_identifiability.jl topology.json report.json")
    exit(1)
end

topo_path, report_path = ARGS[1], ARGS[2]

try
    using StructuralIdentifiability
    using JSON
catch e
    open(report_path, "w") do io
        write(io, "{\"ok\": false, \"method\": \"StructuralIdentifiability.jl\", \"error\": $(repr(string(e))), \"nonidentifiable\": [], \"note\": \"install via julia v2/env/v2_setup.jl\"}")
    end
    exit(0)
end

function write_report(obj)
    open(report_path, "w") do io
        JSON.print(io, obj, 2)
    end
end

try

topo = JSON.parsefile(topo_path)
nodes = String.(topo["nodes"])
edges = topo["edges"]
readouts = [n for n in ("E2F1", "MKI67", "CDKN1A") if n in nodes]
if isempty(readouts)
    readouts = nodes[end:end]
end

safe(name) = replace(String(name), r"[^A-Za-z0-9_]" => "_")
state = Dict(n => safe(n) for n in nodes)
tau = Dict(n => "tau_$(safe(n))" for n in nodes)
kname = ["k_$(i-1)" for i in 1:length(edges)]

lines = String[]
for n in nodes
    terms = ["-$(state[n]) / $(tau[n])"]
    for (i, e) in enumerate(edges)
        if String(e["target"]) != n
            continue
        end
        src = state[String(e["source"])]
        sgn = Int(e["sign"])
        op = sgn < 0 ? "-" : "+"
        push!(terms, "$op $(kname[i]) * $src")
    end
    push!(lines, "    $(state[n])'(t) = " * join(terms, " ") * ",")
end
for (i, n) in enumerate(readouts)
    push!(lines, "    y$i(t) = $(state[n])(t),")
end
# drop trailing comma on last line
lines[end] = rstrip(lines[end], ',')

src = "ode = @ODEmodel(\n" * join(lines, "\n") * "\n)"
ode = eval(Meta.parse(src))

local_map = assess_local_identifiability(ode; prob_threshold = 0.99)
nonident = String[]
status = Dict{String,String}()
identifiable(ok) = ok === true || ok == 1 || ok === :locally || ok === :globally
for (par, ok) in local_map
    pname = string(par)
    flag = identifiable(ok) ? "locally" : "nonidentifiable"
    status[pname] = flag
    if !identifiable(ok)
        # map generated names back to spec keys
        if startswith(pname, "k_")
            push!(nonident, "k[" * replace(pname, "k_" => "") * "]")
        elseif startswith(pname, "tau_")
            gene = replace(pname, "tau_" => "")
            idx = findfirst(==(gene), [safe(n) for n in nodes])
            if idx !== nothing
                push!(nonident, "tau[$(idx-1)]")
            else
                push!(nonident, pname)
            end
        else
            push!(nonident, pname)
        end
    end
end

write_report(Dict(
    "ok" => true,
    "method" => "StructuralIdentifiability.jl_local",
    "package" => "https://github.com/SciML/StructuralIdentifiability.jl",
    "n_nodes" => length(nodes),
    "n_edges" => length(edges),
    "readouts" => readouts,
    "status" => status,
    "nonidentifiable" => sort(unique(nonident)),
    "note" => "linear signed relaxation; n=2 fixed; local identifiability prob_threshold=0.99",
))
catch e
    write_report(Dict(
        "ok" => false,
        "method" => "StructuralIdentifiability.jl",
        "error" => string(e),
        "nonidentifiable" => String[],
        "note" => "identifiability call failed; Python sensitivity fallback",
    ))
end
