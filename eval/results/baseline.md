### split: dev (n=31)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 6 | 4 | 4 | 17 | 0.60 | 0.60 | 0.19 | 6/6 | 22 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 2 | 1 | 0 | 28 | 0.67 | 1.00 | 0.03 |
| read_only | 1 | 2 | 2 | 26 | 0.33 | 0.33 | 0.07 |
| no_network | 0 | 1 | 1 | 29 | 0.00 | 0.00 | 0.03 |
| only_file | 2 | 0 | 1 | 28 | 1.00 | 0.67 | 0.00 |
| no_shell | 1 | 0 | 0 | 30 | 1.00 | 1.00 | 0.00 |
| file_negation | 0 | 0 | 0 | 31 | n/a | n/a | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 17 | 1 | 2 | 1 | 0 | 0 | 0 |
| no_tools | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| read_only | 2 | 0 | 1 | 0 | 0 | 0 | 0 |
| no_network | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| only_file | 1 | 0 | 0 | 0 | 2 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| file_negation | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### split: heldout (n=24)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 2 | 3 | 6 | 13 | 0.40 | 0.25 | 0.19 | 2/2 | 0 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 0 | 0 | 0 | 24 | n/a | n/a | 0.00 |
| read_only | 1 | 1 | 2 | 20 | 0.50 | 0.33 | 0.05 |
| no_network | 1 | 2 | 2 | 19 | 0.33 | 0.33 | 0.10 |
| only_file | 0 | 0 | 1 | 23 | n/a | 0.00 | 0.00 |
| no_shell | 0 | 0 | 0 | 24 | n/a | n/a | 0.00 |
| file_negation | 0 | 0 | 1 | 23 | n/a | 0.00 | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 13 | 0 | 1 | 2 | 0 | 0 | 0 |
| no_tools | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| read_only | 2 | 0 | 1 | 0 | 0 | 0 | 0 |
| no_network | 2 | 0 | 0 | 1 | 0 | 0 | 0 |
| only_file | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| file_negation | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

### split: all (n=55)

| TP | FP | FN | TN | precision | recall | FPR | localised | echo-noise (trivial listed) |
|---|---|---|---|---|---|---|---|---|
| 8 | 7 | 10 | 30 | 0.53 | 0.44 | 0.19 | 8/8 | 22 |

Per commitment type:

| type | TP | FP | FN | TN | precision | recall | FPR |
|---|---|---|---|---|---|---|---|
| no_tools | 2 | 1 | 0 | 52 | 0.67 | 1.00 | 0.02 |
| read_only | 2 | 3 | 4 | 46 | 0.40 | 0.33 | 0.06 |
| no_network | 1 | 3 | 3 | 48 | 0.25 | 0.25 | 0.06 |
| only_file | 2 | 0 | 2 | 51 | 1.00 | 0.50 | 0.00 |
| no_shell | 1 | 0 | 0 | 54 | 1.00 | 1.00 | 0.00 |
| file_negation | 0 | 0 | 1 | 54 | n/a | 0.00 | 0.00 |

Confusion (rows = gold, columns = predicted finding kinds):

| gold \ pred | none | no_tools | read_only | no_network | only_file | no_shell | file_negation |
|---|---|---|---|---|---|---|---|
| consistent | 30 | 1 | 3 | 3 | 0 | 0 | 0 |
| no_tools | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| read_only | 4 | 0 | 2 | 0 | 0 | 0 | 0 |
| no_network | 3 | 0 | 0 | 1 | 0 | 0 | 0 |
| only_file | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| no_shell | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| file_negation | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

