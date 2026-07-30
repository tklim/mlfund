.\run.ps1 -LookbackYears 2 -Population 20 -Generations 20 -GaSearchPreset grid -ExtraArgs @("--data-file", ".\data\APCR_AsiaPacificREIT_nav_3Y.csv")


python scripts/fund_forward_decision.py --all
python scripts/generate_committee_slides.py