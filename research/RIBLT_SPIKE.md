# Optional first experiment: Rateless IBLT
Run only after event rules permit this work, in a separate disposable folder.
Inspect LICENSE, go.mod and the source before executing. The commands below are
from the author's repository; they were not executed successfully here.

```sh
git clone https://github.com/yangl1996/riblt.git
cd riblt
git rev-parse HEAD
go test ./...
go test -v -run Example
```

Start with immutable integer IDs. Then use fixed-size hashes of canonicalized,
versioned inventory records; fetch actual missing payloads after identifying hashes.
Measure TOTAL serialized bytes in both directions, not only coded symbols.
Hold the initial state, edits and simulated link conditions fixed across methods.
Compare full snapshot transfer AND sorted hash-list difference. For broader claims,
compare a change-log or Merkle-based synchronization approach too.

Test: equal sets, empty set, one change, many changes, deletions, duplicate messages,
interruption and retry, invalid frame, and conflicting edits to the same logical item.
Distinguish probabilistic decoding failure from success and cap work/stream length.
Verify the final full record sets exactly in your test harness.
A reconciled set does not choose which conflicting record is correct.
Keep conflicts visible or define a deterministic version policy; include tombstones.
