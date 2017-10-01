
#import toml
#import argparse
#import scipy.optimize
#import re
#import vector_var_index as vvar
#import app_output as app_out
#import lp_constraint_model as lp

# 2017 table (predict it moves with inflation?)
# only married joint at the moment
# Table Columns:
# [braket $ start,
#  bracket size,
#  marginal rate,
#  total tax from all lower brackets ]
marriedjointtax = [
    [0,      18650,   0.10, 0],
    [18650,  57250,   0.15, 1865],
    [75900,  77200,   0.25, 10452.5],
    [153100, 80250,   0.28, 29752.5],
    [233350, 183350,  0.33, 52222.5],
    [416700, 54000,   0.35, 112728],
    [470700, -2,      0.396, 131628]]

# Table Columns:
# [braket $ start,
#  bracket size,
#  marginal rate ]
marriedjointcapitalgains = [
    [0,      75900,   0.0],
    [75900,  394800,  0.15],
    [470700, -3,      0.20]]

taxtable = marriedjointtax
capgainstable = marriedjointcapitalgains

stded = 12700 + 2*4050    # standard deduction + 2 personal exemptions for joint filing

# Account specs contains some initial information 
accountspecs = {'IRA': {'tax': 0.85, 'maxcontrib': 18000+5500*2},
                'roth':{'tax': 1.0, 'maxcontrib': 5500*2},
                'aftertax': {'tax': 0.9, 'basis': 0}}

contribspecs = {'401k': 18000, '401kCatchup': 3000,  'IRARoth': 5500, "IRARothCatchup": 1000, 'CatchupAge': 50}

# Required Minimal Distributions from IRA starting with age 70
RMD = [27.4, 26.5, 25.6, 24.7, 23.8, 22.9, 22.0, 21.2, 20.3, 19.5,  # age 70-79
       18.7, 17.9, 17.1, 16.3, 15.5, 14.8, 14.1, 13.4, 12.7, 12.0,  # age 80-89
       11.4, 10.8, 10.2,  9.6,  9.1,  8.6,  8.1,  7.6,  7.1,  6.7,  # age 90-99
        6.3,  5.9,  5.5,  5.2,  4.9,  4.5,  4.2,  3.9,  3.7,  3.4,  # age 100+
        3.1,  2.9,  2.6,  2.4,  2.1,  1.9,  1.9,  1.9,  1.9,  1.9]

#cg_tax_rate = 0.15       # capital gains tax rate, overall estimate until I get brackets working
penalty = 0.1       # 10% early withdrawal penalty
SS_taxable = 0.85   # maximum portion of SS that is taxable
SS_notTaxable = 1 - SS_taxable