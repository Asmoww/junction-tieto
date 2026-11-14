#!/bin/bash
# Measurement runs: planted-defect branches, plus two repeat runs per real case for stability.
cd "$(dirname "$0")"
job() {  # $1=head $2=req $3=out
  timeout 900 python3 -m reviewer.run --repo sample-repo --base origin/master --head "$1" --req "requirements/REQ-$2.json" \
    --out "$3" --probes evidence/probes.json > "$3.log" 2>&1
}
export -f job
{
  echo "planted-2234 2234 data/measure/planted-2234.json"
  echo "planted-2283 2283 data/measure/planted-2283.json"
  for n in 2283 2234 2129 2297; do for r in 2 3; do echo "origin/ju26-issue-$n $n data/stability/$n-r$r.json"; done; done
} | xargs -P3 -L1 bash -c 'job "$0" "$1" "$2"'
