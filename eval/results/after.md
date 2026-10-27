### split: dev (n=31)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 9 | 0 | 1 | 21 | 1.00 | 0.90 | 0.00 | 9/9 | 0 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 2 | 0 | 0 | 29 | 1.00 | 1.00 | 0.00 |
| read_only | 3 | 0 | 0 | 28 | 1.00 | 1.00 | 0.00 |
| no_network | 0 | 0 | 1 | 30 | n/a | 0.00 | 0.00 |
| only_file | 3 | 0 | 0 | 28 | 1.00 | 1.00 | 0.00 |
| no_shell | 1 | 0 | 0 | 30 | 1.00 | 1.00 | 0.00 |
| file_negation | 0 | 0 | 0 | 31 | n/a | n/a | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 21 | 0 | 0 | 0 | 0 | 0 | 0 |
| no_tools | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| read_only | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| no_network | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| only_file | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| file_negation | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### split: heldout (n=24)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 3 | 2 | 5 | 14 | 0.60 | 0.38 | 0.12 | 3/3 | 0 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 0 | 0 | 0 | 24 | n/a | n/a | 0.00 |
| read_only | 1 | 0 | 2 | 21 | 1.00 | 0.33 | 0.00 |
| no_network | 1 | 2 | 2 | 19 | 0.33 | 0.33 | 0.10 |
| only_file | 1 | 0 | 0 | 23 | 1.00 | 1.00 | 0.00 |
| no_shell | 0 | 0 | 0 | 24 | n/a | n/a | 0.00 |
| file_negation | 0 | 0 | 1 | 23 | n/a | 0.00 | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 14 | 0 | 0 | 2 | 0 | 0 | 0 |
| no_tools | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| read_only | 2 | 0 | 1 | 0 | 0 | 0 | 0 |
| no_network | 2 | 0 | 0 | 1 | 0 | 0 | 0 |
| only_file | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| file_negation | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

### split: all (n=55)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 12 | 2 | 6 | 35 | 0.86 | 0.67 | 0.05 | 12/12 | 0 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 2 | 0 | 0 | 53 | 1.00 | 1.00 | 0.00 |
| read_only | 4 | 0 | 2 | 49 | 1.00 | 0.67 | 0.00 |
| no_network | 1 | 2 | 3 | 49 | 0.33 | 0.25 | 0.04 |
| only_file | 4 | 0 | 0 | 51 | 1.00 | 1.00 | 0.00 |
| no_shell | 1 | 0 | 0 | 54 | 1.00 | 1.00 | 0.00 |
| file_negation | 0 | 0 | 1 | 54 | n/a | 0.00 | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 35 | 0 | 0 | 2 | 0 | 0 | 0 |
| no_tools | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| read_only | 2 | 0 | 4 | 0 | 0 | 0 | 0 |
| no_network | 3 | 0 | 0 | 1 | 0 | 0 | 0 |
| only_file | 0 | 0 | 0 | 0 | 4 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| file_negation | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

