# T12 - repair allocation under budget

200 synthetic evaluation segments, 1000 trials per budget. True damage ~ Beta(2,5)x100; cost = 50,000 mobilisation + 3,000 per damage unit; detector recall 0.75.

| regime | budget | policy | benefit repaired | worst-20 share |
|---|---|---|---|---|
| uniform_traffic | 10% | optimal | 711.8 | 52.1% |
| uniform_traffic | 10% | greedy | 711.6 | 53.9% |
| uniform_traffic | 10% | random | 560.7 | 9.2% |
| uniform_traffic | 20% | optimal | 1,398.7 | 92.4% |
| uniform_traffic | 20% | greedy | 1,398.5 | 100.0% |
| uniform_traffic | 20% | random | 1,132.5 | 19.1% |
| uniform_traffic | 30% | optimal | 2,061.5 | 99.8% |
| uniform_traffic | 30% | greedy | 2,061.3 | 100.0% |
| uniform_traffic | 30% | random | 1,703.6 | 28.9% |
| uniform_traffic | 40% | optimal | 2,701.0 | 100.0% |
| uniform_traffic | 40% | greedy | 2,700.8 | 100.0% |
| uniform_traffic | 40% | random | 2,274.0 | 38.7% |
| uniform_traffic | 50% | optimal | 3,315.0 | 100.0% |
| uniform_traffic | 50% | greedy | 3,314.9 | 100.0% |
| uniform_traffic | 50% | random | 2,845.9 | 49.2% |
| varying_traffic | 10% | optimal | 2,525.0 | 69.0% |
| varying_traffic | 10% | greedy | 2,425.0 | 72.5% |
| varying_traffic | 10% | random | 770.8 | 9.6% |
| varying_traffic | 20% | optimal | 3,871.0 | 95.3% |
| varying_traffic | 20% | greedy | 3,743.5 | 100.0% |
| varying_traffic | 20% | random | 1,549.9 | 19.5% |
| varying_traffic | 30% | optimal | 4,858.2 | 99.7% |
| varying_traffic | 30% | greedy | 4,729.0 | 100.0% |
| varying_traffic | 30% | random | 2,334.8 | 29.4% |
| varying_traffic | 40% | optimal | 5,632.5 | 100.0% |
| varying_traffic | 40% | greedy | 5,513.9 | 100.0% |
| varying_traffic | 40% | random | 3,115.3 | 39.3% |
| varying_traffic | 50% | optimal | 6,255.6 | 100.0% |
| varying_traffic | 50% | greedy | 6,150.4 | 100.0% |
| varying_traffic | 50% | random | 3,889.9 | 49.2% |
