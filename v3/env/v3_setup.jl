# Pipeline v2 Julia environment (NB09 structural identifiability).
# Usage: julia v3/env/v3_setup.jl
using Pkg
root = dirname(@__FILE__)
proj = joinpath(root, "julia")
mkpath(proj)
Pkg.activate(proj)
Pkg.add(["StructuralIdentifiability", "JSON"])
Pkg.instantiate()
println("Julia project ready at ", proj)
println("  julia --project=", proj, " -e 'using StructuralIdentifiability, JSON'")
