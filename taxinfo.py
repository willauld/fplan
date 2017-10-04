

# 2017 table (predict it moves with inflation?)
# married joint, married separate, single
# Table Columns:
# [braket $ start,
#  bracket size,
#  marginal rate,
#  total tax from all lower brackets ] ### TODO check if this field is used delete if not!
marriedjointtax = [
    [0,      18650,   0.10, 0],
    [18650,  57250,   0.15, 1865],
    [75900,  77200,   0.25, 10452.5],
    [153100, 80250,   0.28, 29752.5],
    [233350, 183350,  0.33, 52222.5],
    [416700, 54000,   0.35, 112728],
    [470700, -2,      0.396, 131628]]

marriedseparatetax = [
    [0,         9325,   0.10,   0],
    [9325,      28625,  0.15,   932.5],
    [37950,     38900,  0.25,   5226.25],
    [76550,     40125,  0.28,   14876.25],
    [116675,    91675,  0.33,   26111.25],
    [208350,    27000,  0.35,   56364.00],
    [235350,    -2,     0.396,  65814.00]]

singletax = [
    [0,         9325,   0.10,   0],
    [9325,      28625,  0.15,   932.5],
    [37950,     53950,  0.25,   5226.25],
    [91900,     99750,  0.28,   18713.75],
    [191650,    225050, 0.33,   46643.75],
    [416700,    1700,   0.35,   120910.25],
    [418,400,   -2,     0.396,  121505.25]]

# Table Columns:
# [braket $ start,
#  bracket size,
#  marginal rate ]
marriedjointcapitalgains = [
    [0,      75900,   0.0],
    [75900,  394800,  0.15],
    [470700, -3,      0.20]]

marriedseparatecapitalgains = [
    [0,         76550,  0.0],
    [76550,     158800, 0.15],
    [235350,    -3,     0.20]]

singlecapitalgains = [
    [0,         37950,  0.0],
    [37950,     380450,  0.15],
    [418400,    -3,     0.20]]

# Required Minimal Distributions from IRA starting with age 70 
# https://www.irs.gov/publications/p590b#en_US_2016_publink1000231258
# Using appendix B table III in all cases.
marriedjointRMD = [
        27.4, 26.5, 25.6, 24.7, 23.8, 22.9, 22.0, 21.2, 20.3, 19.5,  # age 70-79
        18.7, 17.9, 17.1, 16.3, 15.5, 14.8, 14.1, 13.4, 12.7, 12.0,  # age 80-89
        11.4, 10.8, 10.2,  9.6,  9.1,  8.6,  8.1,  7.6,  7.1,  6.7,  # age 90-99
        6.3,  5.9,  5.5,  5.2,  4.9,  4.5,  4.2,  3.9,  3.7,  3.4,   # age 100+
        3.1,  2.9,  2.6,  2.4,  2.1,  1.9,  1.9,  1.9,  1.9,  1.9]

marriedseparateRMD = marriedjointRMD 
singleRMD = marriedjointRMD 

marriedjointstded = 12700 + 2*4050 # standard deduction + 2 personal exemptions
marriedseparatestded = 9350 + 4050 # standard deduction + 1 personal exemptions
singlestded = 6350 + 4050          # standard deduction + 1 personal exemptions

taxtable = marriedjointtax
capgainstable = marriedjointcapitalgains
stded = marriedjointstded
RMD = marriedjointRMD

# Account specs contains some initial information # TODO if maxcontrib not used delete
accountspecs = {'IRA': {'tax': 0.85, 'maxcontrib': 18000+5500*2},
                'roth':{'tax': 1.0, 'maxcontrib': 5500*2},
                'aftertax': {'tax': 0.9, 'basis': 0}}

contribspecs = {'401k': 18000, '401kCatchup': 3000,  'IRARoth': 5500, "IRARothCatchup": 1000, 'CatchupAge': 50}

penalty = 0.1       # 10% early withdrawal penalty
SS_taxable = 0.85   # maximum portion of SS that is taxable
SS_notTaxable = 1 - SS_taxable