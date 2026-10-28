# P2P Lending Matchmaking - Evaluation Report

Funding mode: full funding. Simulated data only.

| Lenders | Requests | Pairs | Match time (s) | Eligible | Selected | Matched | Success % | Violations | Explanations | Consistency |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 21 | 210 | 0.018 | 52 | 14 | 14 | 66.7 | 0 | 210/210 | 8/8 |
| 50 | 105 | 5250 | 0.135 | 1608 | 85 | 85 | 81.0 | 0 | 5250/5250 | 8/8 |
| 200 | 385 | 77000 | 2.452 | 21179 | 297 | 297 | 77.1 | 0 | 77000/77000 | 8/8 |

## Consistency checks (largest run)

- [x] every loan has a LOAN_CREATED audit entry
- [x] every loan has one instalment per month
- [x] outstanding balance matches settled instalments
- [x] funded requests: loan principals add up to the request amount
- [x] no lender has negative available funds
- [x] accepted matches == loans
- [x] every repayment status change is in the audit log
- [x] funded requests have loans
