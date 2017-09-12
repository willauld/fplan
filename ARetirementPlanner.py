#!/usr/bin/python3

#
# A Retirement Planner (optimize withdrawals for most efficient use of the nest egg)
#

import toml
import argparse
import scipy.optimize
import re
import sys

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

accounttable = [] # array of [bal, rate, discount] # TODO update this comment
    # discount represents the value of the account balance (after a sort of tax)
    # The discount is approximently a cost of using the money in the account

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

def get_max_bracket(year, expect_total, printErrors):
    i_mul = S.i_rate ** year
    s = 0
    for k in range(len(taxtable)):
        (cut, size, rate, base) = taxtable[k]
        cut *= i_mul
        size *= i_mul
        base *= i_mul
        s += res.x[index_x(year,k)]
        if k == len(taxtable) -1 or res.x[index_x(year,k+1)] ==0 :
            break
    if printErrors:
        if (expect_total + 0.1 < s) or (expect_total - 0.1 > s):
            print("max_bracket: cut: %6.1f size: %6.1f rate: %3.3f base: %6.1f lastBrakAmt: %6.1f brakSum: %6.1f" % (cut, size, rate, base, res.x[index_x(year,k)], s), flush=True)
            print("Error(year %d): Expected bracket sum to be %6.2f but is %6.2f" % (year, expect_total, s))
    return cut, size, rate, base, res.x[index_x(year,k)], s

def agelist(str):
    for x in str.split(','):
        m = re.match('^(\d+)(-(\d+)?)?$', x)
        if m:
            s = int(m.group(1))
            e = s
            if m.group(2):
                e = m.group(3)
                if e:
                    e = int(e)
                else:
                    e = 120
            for a in range(s,e+1):
                yield a
        else:
            raise Exception("Bad age " + str)

class Data:
    def check_record(self, dict, type, fields):
        ##
        ## This routine looks a the categories and they labeled components (keys) to 
        ## ensure a uniform structure for later processing
        ##
        rec = dict.get(type,{}) 
        temp = {}
        numNotIn = 0
        numIn = 0
        for f in rec:
            if f not in fields:
                numNotIn += 1
                #print("\nWarning: field(%s) does not match record(%s) fields, fixing up."%(f,type))
                temp = {f: rec[f]}
            else:
                numIn += 1
        if numIn > 0: # and numNotIn > 0:
            for f in temp:
                del rec[f]
            dict[type] = {'nokey': rec} # add the 'nokey' key for the record without a key value
            for f in temp:
                dict[type][f] = temp[f]

    def match_retiree(self, retireekey):
        for v in self.retiree:
            #print("    retiree: ", v)
            if v['mykey'] == retireekey:
                return v
        return None
        
    def rmd_needed(self,year,retireekey):
        rmd = 0
        #print("RMD_NEEDED: year: %d, retireekey: %s" % (year, retireekey))
        v = self.match_retiree(retireekey)
        age = v['ageAtStart']+year
        if age >= 70: # IRA retirement: minimum distribution starting age 70.5 
            rmd = RMD[age - 70]
            #print("rmd: %d, age: %d, retiree: %s" % (rmd, age, retireekey))
        return rmd

    def apply_early_penalty(self,year,retireekey):
        response = False
        v = self.match_retiree(retireekey)
        age = v['ageAtStart']+year
        if age < 60: # IRA retirement account require penalty if withdrawn before age 59.5
            response = True
        return response

    def load_file(self, file):

        def get_account_info(type):
            index = 0
            lis_return = []
            for k,v in d.get( type , {}).items():
                entry = {}
                entry['acctype'] = type
                entry['index'] = index
                entry['estateTax'] = accountspecs[type]['tax']
                entry['bal'] = v['bal']
                entry['mykey'] = k
                if type == 'IRA' or type == 'roth':
                    r = self.match_retiree(k)
                    if r is None:
                        print("Error: Account must match a retiree\n\t[%s.%s] should match [iam.%s] but there is no [iam.%s]\n"%(type,k,k,k))
                        exit(1)
                    if 'maxcontrib' not in v:
                        mxcontrib = accountspecs[type]['maxcontrib']
                        entry['maxcontrib'] = mxcontrib
                        v['maxcontrib'] = mxcontrib
                    else:
                        entry['maxcontrib'] = v['maxcontrib']
                else:  
                    assert type == 'aftertax'
                    if 'basis' not in v:
                        entry['basis'] = 0
                        v['basis'] = 0
                    else:
                        entry['basis'] = v['basis']
                if 'rate' not in v:
                    entry['rate'] = self.r_rate 
                    v['rate'] = self.r_rate 
                else:
                    rate = 1 + v['rate'] / 100  # invest rate: 6 -> 1.06
                    entry['rate'] = rate
                    v['rate'] = rate
                lis_return.append(entry)
                index += 1
            return lis_return

        def get_retiree_info():
            type = 'iam'
            indx = 0
            lis_return = []
            yearstoretire = [0,0]
            yearsthrough = [0,0]
            for k,v in d.get( type , {}).items():
                entry = {}
                entry['primary'] = v.get('primary', False) 
                entry['index'] = indx
                entry['age'] = v['age']
                entry['retire'] = v['retire']
                if entry['retire'] < entry['age']:
                    entry['retire'] = entry['age']
                entry['through'] = v['through']
                entry['mykey'] = k
                yearstoretire[indx]=entry['retire']-entry['age']
                yearsthrough[indx]=entry['through']-entry['age']+1
                lis_return.append(entry)
                indx += 1
            delta = 0
            start = entry['retire']
            lis_return[0]['ageAtStart'] = start
            end = yearsthrough[0]+lis_return[0]['age']
            primaryIndx = 0
            secondaryIndx = 1
            if indx > 1:
                if lis_return[0]['primary'] == lis_return[1]['primary']:
                    print("Error: one of two retirees must be primary (i.e., primary = true):")
                    print("    [iam.%s] primary == %s" % (lis_return[0]['mykey'], lis_return[0]['primary']))
                    print("    [iam.%s] primary == %s" % (lis_return[1]['mykey'], lis_return[1]['primary']))
                    exit(1)
                if lis_return[1]['primary'] == True:
                    primaryIndx = 1
                    secondaryIndx = 0
                delta = lis_return[primaryIndx]['age'] - lis_return[secondaryIndx]['age']
                start = min(yearstoretire[0], yearstoretire[1]) + lis_return[primaryIndx]['age']
                lis_return[primaryIndx]['ageAtStart'] = start
                lis_return[secondaryIndx]['ageAtStart'] = start - delta
                end = max(yearsthrough[0], yearsthrough[1])+lis_return[primaryIndx]['age']
            #print("delta: %d, start: %d, end: %d, numyr: %d" %(delta, start, end, end-start))
            return lis_return, start, end-start, lis_return[primaryIndx]['mykey']

        self.accounttable = []
        with open(file) as conffile:
            d = toml.loads(conffile.read())
        #print("\n\nun tarnished dict: ", d)
        #for f in d:
        #    print("\ndict[%s] = " % (f),d[f])
        #print()
        
        self.check_record( d, 'iam', ('age', 'retire', 'through', 'primary'))
        self.check_record( d, 'SocialSecurity', ('FRA', 'age', 'amount'))
        self.check_record( d, 'IRA', ('bal', 'rate', 'maxcontrib'))
        self.check_record( d, 'roth', ('bal', 'rate', 'maxcontrib'))
        self.check_record( d, 'aftertax', ('bal', 'rate', 'basis'))
        self.check_record( d, 'expense', ('amount', 'age', 'inflation', 'tax'))
        self.check_record( d, 'income', ('amount', 'age', 'inflation', 'tax'))
        self.check_record( d, 'desired', ('amount', 'age', 'inflation', 'tax'))
        self.check_record( d, 'max', ('amount', 'age', 'inflation', 'tax'))
        #print("\n\ntarnished dict: ", d)
        #for f in d:
        #    print("\ndict[%s] = " % (f),d[f])
        #print()
        #exit(0)
        self.retirement_type = d.get('retirement_type', 'joint') # single, joint,...
        self.maximize = d.get('maximize',"Spending") # what to maximize for: Spending or PlusEstate 

        self.i_rate = 1 + d.get('inflation', 0) / 100       # inflation rate: 2.5 -> 1.025
        self.r_rate = 1 + d.get('returns', 6) / 100         # invest rate: 6 -> 1.06

        self.retiree, self.startage, self.numyr, self.who = get_retiree_info() # returns entry for each retiree
        #print("\nself.retiree: ", self.retiree, "\n\n")
        
        #print("input dictionary(processed): ", d)
        self.accounttable += get_account_info('IRA') # returns entry for each account
        self.accounttable += get_account_info('roth') 
        self.accounttable += get_account_info('aftertax') 
        #print("++Accounttable: ", self.accounttable)

        self.accmap = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(self.accounttable)):
            self.accmap[self.accounttable[j]['acctype']] += 1
        print("Account Map ", self.accmap)

        self.SSinput = [{}, {}] 
        self.parse_expenses(d)

        #print("input dictionary(processed): ", d)

    def parse_expenses(self, S):
        """ Return array of income/expense per year """

        def startamount(amount, fra, start):
            if start > 70:
                start = 70
            if start < 62:
                start = 62
            if start < fra:
                return amount/(1.067**(fra-start))
            if start >= fra:
                return amount*(1.08**(start-fra))

        def do_SS_details(bucket):
            sections = 0
            index = 0
            type = 'SocialSecurity'
            for k,v in S.get( type , {}).items():
                sections += 1
                r = self.match_retiree(k)
                if r is None:
                    print("Error: [%s.%s] must match a retiree\n\t[%s.%s] should match [iam.%s] but there is no [iam.%s]\n"%(type,k,type,k,k,k))
                    exit(1)
                fraamount = v['amount']
                fraage = v['FRA']
                agestr = v['age']
                dt = {'key': k, 'amount': fraamount, 'fra': fraage, 'agestr': agestr, 'ageAtStart': r['ageAtStart']}
                if fraamount < 0 and sections == 1: # default spousal support in second slot
                    self.SSinput[1] = dt
                else:
                    self.SSinput[index] = dt
                    index += 1

            for i in range(sections):
                #print("SSinput", self.SSinput)
                agestr = self.SSinput[i]['agestr']
                firstage = agelist(agestr)
                disperseage = next(firstage)
                fraage = self.SSinput[i]['fra']
                fraamount = self.SSinput[i]['amount']
                ageAtStart = self.SSinput[i]['ageAtStart']
                if fraamount < 0:
                    assert i == 1
                    fraamount = self.SSinput[0]['amount']/2 # spousal benefit is 1/2 spouses at FRA 
                    # alter amount for start age vs fra (minus if before fra and + is after)
                    amount = startamount(fraamount, fraage, min(disperseage,fraage))
                else:
                    # alter amount for start age vs fra (minus if before fra and + is after)
                    amount = startamount(fraamount, fraage, disperseage)
                #print("FRA: %d, FRAamount: %6.0f, Age: %s, amount: %6.0f" % (fraage, fraamount, agestr, amount))
                for age in agelist(agestr):
                    year = age - ageAtStart #self.startage
                    if year < 0:
                        continue
                    elif year >= self.numyr:
                        break
                    else:
                        adj_amount = amount * self.i_rate ** year
                        #print("age %d, year %d, bucket: %6.0f += amount %6.0f" %(age, year, bucket[year], adj_amount))
                        bucket[year] += adj_amount

        def do_details(category, bucket, tax):
            #print("CAT: %s" % category)
            for k,v in S.get(category, {}).items():
                #print("K = %s, v = " % k,v)
                for age in agelist(v['age']):
                    #print("age %d, startage %d, year %d" % (age, self.startage, age-self.startage))
                    year = age - self.startage
                    if year < 0:
                        continue
                    elif year >= self.numyr:
                        break
                    else:
                        amount = v['amount']
                        #print("amount %6.0f, " % (amount), end='')
                        if v.get('inflation'):
                            amount *= self.i_rate ** year
                        #print("inf amount %6.0f, year %d, curbucket %6.0f" % (amount , year, bucket[year]), end='')
                        bucket[year] += amount
                        #print("newbucket %6.0f" % (bucket[year]))
                        if tax != 0 and v.get('tax'):
                            tax[year] += amount

        INC = [0] * self.numyr
        EXP = [0] * self.numyr
        TAX = [0] * self.numyr
        WANT = [0] * self.numyr
        MAX = [0] * self.numyr
        SS = [0] * self.numyr

        do_details("expense", EXP, 0)
        do_details("income", INC, TAX)
        do_details("desired", WANT, 0)
        do_details("max", MAX, 0)
        do_SS_details(SS)

        self.income = INC
        self.expenses = EXP # WGA not currently in use
        self.taxed = TAX
        self.desired = WANT
        self.max = MAX
        self.SS = SS 

# Minimize: c^T * x
# Subject to: A_ub * x <= b_ub
#all vars positive
def solve():

    A = []
    b = []

    c = [0] * nvars
    #
    # Add objective function (S1') becomes (R1') if PlusEstate is added
    #
    for year in range(S.numyr):
        c[index_s(year)] = -1
    #
    # Add objective function tax bracket forcing function (EXPERIMENTAL)
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)):
            # multiplies the impact of higher brackets opposite to optimization
            # the intent here is to pressure higher brackets more and pack the 
            # lower brackets
            c[index_x(year,k)] = k/10 
    #
    # Adder objective function (R1') when PlusEstate is added
    #
    if S.maximize == "PlusEstate":
        for j in range(len(accounttable)):
            c[index_b(S.numyr,j)] = -1*accounttable[j]['estateTax'] # account discount rate
        print("\nConstructing Spending + Estate Model:\n")
    else:
        print("\nConstructing Spending Model:\n")
        startamount = 0
        for j in range(len(accounttable)):
            startamount += accounttable[j]['bal']
        balancer = 1/(startamount) 
        for j in range(len(accounttable)):
            c[index_b(S.numyr,j)] = -1*balancer *accounttable[j]['estateTax'] # balance and discount rate
    
    #
    # Add constraint (2' try)
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(accounttable)):
            p = 1
            if accounttable[j]['acctype'] != 'aftertax':
                if S.apply_early_penalty(year,accounttable[j]['mykey']):
                    p = 1-penalty
            row[index_w(year,j)] = -1*p 
        for k in range(len(taxtable)): 
            row[index_x(year,k)] = taxtable[k][2] # income tax
        if S.accmap['aftertax'] > 0:
            for l in range(len(capgainstable)): 
                row[index_y(year,l)] = capgainstable[l][2] # cap gains tax
            row[index_D(year)] = 1
        row[index_s(year)] = 1
        A+=[row]
        b+=[S.income[year] + S.SS[year]]
    #
    # Add constraint (3a')
    #
    for year in range(S.numyr-1):
        row = [0] * nvars
        row[index_s(year+1)] = 1
        row[index_s(year)] = -1*S.i_rate
        A+=[row]
        b+=[0]
    #
    # Add constraint (3b')
    #
    for year in range(S.numyr-1):
        row = [0] * nvars
        row[index_s(year)] = S.i_rate
        row[index_s(year+1)] = -1
        A+=[row]
        b+=[0]
    #
    # Add constrant (4') rows - not needed if [desired.income] is not defined in input
    #
    if S.desired[0] != 0:
        for year in range(1): # Only needs setting at the beginning
            row = [0] * nvars
            row[index_s(year)] = -1
            A+=[row]
            b+=[ - S.desired[year] ]     # [- d_i]

    #
    # Add constraints for (5') rows - not added if [max.income] is not defined in input
    #
    if S.max[0] != 0:
        for year in range(1): # Only needs to be set at the beginning
            row = [0] * nvars
            row[index_s(year)] = 1
            A+=[row]
            b+=[ S.max[year] ]     # [ dm_i]

    #
    # Add constaints for (6') rows
    #
    for year in range(S.numyr):
        for j in range(min(2,len(accounttable))): # at most the first two accounts are type IRA w/ RMD requirement
            if accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,accounttable[j]['mykey'])
                if rmd > 0:
                    row = [0] * nvars
                    row[index_b(year,j)] = 1/rmd 
                    row[index_w(year,j)] = -1
                    A+=[row]
                    b+=[0]

    #
    # Add constraints for (7a')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for k in range(len(taxtable)):
            row[index_x(year,k)] = 1
        for j in range(len(accounttable)):
            if accounttable[j]['acctype'] == 'IRA':
                row[index_w(year,j)] = -1 # Account 0 is TDRA
        A+=[row]
        b+=[S.taxed[year]+SS_taxable*S.SS[year]-stded*adj_inf]
    #
    # Add constraints for (7b')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for j in range(len(accounttable)):
            if accounttable[j]['acctype'] == 'IRA':
                row[index_w(year,j)] = 1 # Account 0 is TDRA
        for k in range(len(taxtable)):
            row[index_x(year,k)] = -1
        A+=[row]
        b+=[stded*adj_inf-S.taxed[year]-SS_taxable*S.SS[year]]
    #
    # Add constraints for (8')
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)-1):
            row = [0] * nvars
            row[index_x(year,k)] = 1
            A+=[row]
            b+=[(taxtable[k][1])*(S.i_rate**year)] # inflation adjusted
    #
    # Add constraints for (9a')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            f = cg_taxable_fraction(year)
            row = [0] * nvars
            for l in range(len(capgainstable)):
                row[index_y(year,l)] = 1
            j = len(accounttable)-1
            row[index_w(year,j)] = -1*f # last Account is investment / stocks
            A+=[row]
            b+=[0]
    #
    # Add constraints for (9b')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            f = cg_taxable_fraction(year)
            row = [0] * nvars
            j = len(accounttable)-1
            row[index_w(year,j)] = f # last Account is investment / stocks
            for l in range(len(capgainstable)):
                row[index_y(year,l)] = -1
            A+=[row]
            b+=[0]
    #
    # Add constraints for (10')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            adj_inf = S.i_rate**year
            for l in range(len(capgainstable)-1):
                row = [0] * nvars
                row[index_y(year,l)] = 1
                for k in range(len(taxtable)-1):
                    if taxtable[k][0] >= capgainstable[l][0] and taxtable[k][0] < capgainstable[l+1][0]:
                        row[index_x(year,k)] = 1
                A+=[row]
                b+=[capgainstable[l][1]*adj_inf] # mcg[i,l] inflation adjusted
                #print_constraint( row, capgainstable[l][1]*adj_inf)
    #
    # Add constraints for (11a')
    #
    aftertax = 0
    if S.accmap['aftertax'] > 0:
        aftertax = 1
    for year in range(S.numyr): 
        for j in range(len(accounttable)-aftertax): # for all accounts except aftertax
            row = [0] * nvars
            row[index_b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[index_b(year,j)] = -1*accounttable[j]['rate']
            row[index_w(year,j)] = accounttable[j]['rate']
            A+=[row]
            b+=[0]
    #
    # Add constraints for (11b')
    #
    aftertax = 0
    if S.accmap['aftertax'] > 0:
        aftertax = 1
    for year in range(S.numyr):
        for j in range(len(accounttable)-aftertax): # for all accounts except aftertax
            row = [0] * nvars
            row[index_b(year,j)] = accounttable[j]['rate']
            row[index_w(year,j)] = -1*accounttable[j]['rate']
            row[index_b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #
    # Add constraints for (12a')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr): 
            j = len(accounttable)-1 # nl the last account, the investment account
            row = [0] * nvars
            row[index_b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[index_b(year,j)] = -1*accounttable[j]['rate']
            row[index_w(year,j)] = accounttable[j]['rate']
            row[index_D(year)] = -1*accounttable[j]['rate']
            A+=[row]
            b+=[0]
    #
    # Add constraints for (12b')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            j = len(accounttable)-1 # nl the last account, the investment account
            row = [0] * nvars
            row[index_b(year,j)] = accounttable[j]['rate']
            row[index_w(year,j)] = -1*accounttable[j]['rate']
            row[index_D(year)] = accounttable[j]['rate']
            row[index_b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #
    # Constraint for (13a')
    #   Set the begining b[1,j] balances
    #
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = 1
        A+=[row]
        b+=[accounttable[j]['bal']]
    #
    # Constraint for (13b')
    #   Set the begining b[1,j] balances
    #
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = -1
        A+=[row]
        b+=[-1*accounttable[j]['bal']]
    #
    # Constrant for (14') is default for sycpy so no code is needed
    #
    if args.verbose:
        print("Num vars: ", len(c))
        print("Num contraints: ", len(b))
        print()

    res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                 options={"disp": args.verbose,
                                          #"bland": True,
                                          "tol": 1.0e-7,
                                          "maxiter": 3000})
    if args.verbosemodel or args.verbosemodelall:
        print_model_matrix(c, A, b, res.slack, non_binding_only)
    if args.verbosewga:
        print(res)

    if res.success == False:
        print(res)
        exit(1)

    return res

def print_model_matrix(c, A, b, s, non_binding_only):
    if not non_binding_only:
        print("c: ")
        print_model_row(c)
        print()
        print("B? i: A_ub[i]: b[i]")
        for constraint in range(len(A)):
            if s[constraint] >0:
                print("  ", end='')
            else:
                print("B ", end='')
            print(constraint, ": ", sep='', end='')
            print_constraint( A[constraint], b[constraint])
    else:
        print(" i: A_ub[i]: b[i]")
        j = 0
        for constraint in range(len(A)):
            if s[constraint] >0:
                j+=1
                print(constraint, ": ", sep='', end='')
                print_constraint( A[constraint], b[constraint])
        print("\n\n%d non-binding constrains printed\n" % j)
    print()

def consistancy_check(res):
    def do_check_index_sequence():
        # index_?() functions are laid out to index a vector of variables 
        # laid out in the order x(i,k), y(i,l), w(i,j), b(i,j), s(i), D(i), ns()
        ky = 0
        row = [0] * nvars
        for i in range(S.numyr):
            for k in range(len(taxtable)):
                if index_x(i, k) != ky:
                    print("index_x(%d,%d) is %d not %d as it should be" % (i,k,index_x(i,k), ky))
                ky+=1
        if S.accmap['aftertax'] > 0:
            for i in range(S.numyr):
                for l in range(len(capgainstable)):
                    if index_y(i, l) != ky:
                        print("index_y(%d,%d) is %d not %d as it should be" % (i,l,index_y(i,l), ky))
                    ky+=1
        for i in range(S.numyr):
            for j in range(len(accounttable)):
                if index_w(i, j) != ky:
                    print("index_w(%d,%d) is %d not %d as it should be" % (i,j,index_w(i,j), ky))
                ky+=1
        for i in range(S.numyr+1): # b[] has an extra year
            for j in range(len(accounttable)):
                if index_b(i, j) != ky:
                    print("index_b(%d,%d) is %d not %d as it should be" % (i,j, index_b(i,j), ky))
                ky+=1
        for i in range(S.numyr):
            if index_s(i) != ky:
                    print("index_s(%d) is %d not %d as it should be" % (i, index_s(i), ky))
            ky+=1
        if S.accmap['aftertax'] > 0:
            for i in range(S.numyr):
                if index_D(i) != ky:
                    print("index_D(%d) is %d not %d as it should be" % (i,index_D(i), ky))
                ky+=1

    # check to see if the ordinary tax brackets are filled in properly
    print()
    print()
    print("Consistancy Checking:")
    print()

    do_check_index_sequence()

    for year in range(S.numyr):
        s = 0
        fz = False
        fnf = False
        i_mul = S.i_rate ** year
        for k in range(len(taxtable)): 
            cut, size, rate, base = taxtable[k]
            size *= i_mul
            s += res.x[index_x(year,k)] 
            if fnf and res.x[index_x(year,k)] > 0:
                print("Inproper packed brackets in year %d, bracket %d not empty while previous bracket not full." % (year, k))
            if res.x[index_x(year,k)]+1 < size:
                fnf = True
            if fz and res.x[index_x(year,k)] > 0:
                print("Inproperly packed tax brackets in year %d bracket %d" % (year, k))
            if res.x[index_x(year,k)] == 0.0:
                fz = True
        if S.accmap['aftertax'] > 0:
            scg = 0
            fz = False
            fnf = False
            for l in range(len(capgainstable)): 
                cut, size, rate = capgainstable[l]
                size *= i_mul
                bamount = res.x[index_y(year,l)] 
                scg += bamount
                for k in range(len(taxtable)-1):
                    if taxtable[k][0] >= capgainstable[l][0] and taxtable[k][0] < capgainstable[l+1][0]:
                        bamount += res.x[index_x(year,k)]
                if fnf and bamount > 0:
                    print("Inproper packed CG brackets in year %d, bracket %d not empty while previous bracket not full." % (year, l))
                if bamount+1 < size:
                    fnf = True
                if fz and bamount > 0:
                    print("Inproperly packed GC tax brackets in year %d bracket %d" % (year, l))
                if bamount == 0.0:
                    fz = True
        #TaxableOrdinary = res.x[index_w(year,0)] + S.income[year] -stded*i_mul
        TaxableOrdinary = OrdinaryTaxable(year)
        if (TaxableOrdinary + 0.1 < s) or (TaxableOrdinary - 0.1 > s):
            print("Error: Expected (age:%d) Taxable Ordinary income %6.2f doesn't match bracket sum %6.2f" % 
                (year + S.startage, TaxableOrdinary,s))

        for j in range(len(accounttable)-1):
            a = res.x[index_b(year+1,j)] -( res.x[index_b(year,j)] - res.x[index_w(year,j)])*accounttable[0]['rate']
            if a > 1:
                print("account[%d] year to year balance NOT OK years %d to %d" % (j, year, year+1))
                print("difference is", a)

        last = len(accounttable)-1
        D = 0
        if S.accmap['aftertax'] > 0:
            D = res.x[index_D(year)]
        if res.x[index_b(year+1,last)] -( res.x[index_b(year,last)] - res.x[index_w(year,last)] + D)*accounttable[0]['rate']>1:
            print("account[%d] year to year balance NOT OK years %d to %d" % (2, year, year+1))

        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        if spendable + 0.1 < res.x[index_s(year)]  or spendable -0.1 > res.x[index_s(year)]:
            print("Calc Spendable %6.2f should equal s(year:%d) %6.2f"% (spendable, year, res.x[index_s(year)]))
            print("w[%d,0]: %6.0f +w[%d,1]: %6.0f +w[%d,2]: %6.0f -D[%d]: %6.0f +o[%d]: %6.0f +SS[%d]: %6.0f -tax: %6.0f -cg_tax: %6.0f" % (year, res.x[index_w(year,0)] ,year, res.x[index_w(year,1)] ,year, res.x[index_w(year,2)] ,year, res.x[index_D(year)] ,year, S.income[year] ,year, S.SS[year] , tax ,cg_tax))
        bt = 0
        for k in range(len(taxtable)):
            bt += res.x[index_x(year,k)] * taxtable[k][2]
        if tax + 0.1 < bt  or tax -0.1 > bt:
            print("Calc tax %6.2f should equal brackettax(bt)[]: %6.2f" % (tax, bt))
        #if cg_tax + 0.1 < res.x[index_Fcg(year)]  or cg_tax -0.1 > res.x[index_Fcg(year)]:
        #    print("Calc cg_tax %6.2f should equal Fcg(year:%d): %6.2f" % (cg_tax, year, res.x[index_Fcg(year)]))
    print()

def output(string): # TODO move to a better place
    #
    # output writes the information after first changing any '@' in the string
    # to a space for stdout or a ',' for csv files. The later is written
    # whenever the csv_file handle is not None
    #
    sys.stdout.write(string.replace('@',' '))
    if csv_file is not None:
        csv_file.write(string.replace('@',','))

def print_model_results(res): 
    def printheader1():
        output("%s\n" % S.who)
        output((" age" + "@%7s" * 12) % ("IRA", "fIRA", "RMDref", "Roth", "fRoth", "AftaTx", "fAftaTx", "tAftaTx", "o_inc", "SS", "TFedTax", "Spndble"))
        output("\n")

    output("\nActivity Summary:\n")
    output('\n')
    printheader1()
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        age = year + S.startage
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)

        rmdref = 0
        for j in range(min(2,len(accounttable))): # at most the first two accounts are type IRA w/ RMD requirement
            if accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref += res.x[index_b(year,j)]/rmd 

        balance = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(accounttable)):
            balance[accounttable[j]['acctype']] += res.x[index_b(year,j)]
            withdrawal[accounttable[j]['acctype']] += res.x[index_w(year,j)]
        D = 0
        if S.accmap['aftertax'] > 0:
            D = res.x[index_D(year)]/1000.0

        output(("%3d:" + "@%7.0f" * 12 ) %
              (year+S.startage, 
              balance['IRA']/1000.0, withdrawal['IRA']/1000.0, rmdref/1000.0, # IRA
              balance['roth']/1000.0, withdrawal['roth']/1000.0, # Roth
              balance['aftertax']/1000.0, withdrawal['aftertax']/1000.0, D, # AftaTax
              S.income[year]/1000.0, S.SS[year]/1000.0,
              (tax+cg_tax+earlytax)/1000.0, res.x[index_s(year)]/1000.0) )
        output("\n")

    year = S.numyr
    balance = {'IRA': 0, 'roth': 0, 'aftertax': 0}
    for j in range(len(accounttable)):
        balance[accounttable[j]['acctype']] += res.x[index_b(year,j)]
    output(("%3d:" + "@%7.0f@%7s@%7s" + "@%7.0f@%7s" * 2 + "@%7s" * 5) %
        (year+S.startage, 
        balance['IRA']/1000.0, '-', '-',  # res.x[index_w(year,0)]/1000.0, # IRA
        balance['roth']/1000.0, '-', # res.x[index_w(year,1)]/1000.0, # Roth
        balance['aftertax']/1000.0, '-', # res.x[index_w(year,2)]/1000.0, # AftaTax
        '-', '-', '-', '-', '-'))
    output("\n")
    printheader1()

def print_account_trans(res):
    def print_acc_header1():
        output("%s\n" % S.who)
        output(" age")
        if S.accmap['IRA'] >1:
            output(("@%7s" * 6) % ("IRA1", "fIRA1", "RMDref1", "IRA2", "fIRA2", "RMDref2"))
        elif S.accmap['IRA'] == 1:
            output(("@%7s" * 3) % ("IRA", "fIRA", "RMDref"))
        if S.accmap['roth'] >1:
            output(("@%7s" * 4) % ("Roth1", "fRoth1", "Roth2", "fRoth2"))
        elif S.accmap['roth'] == 1:
            output(("@%7s" * 2) % ("Roth", "fRoth"))
        if S.accmap['IRA']+S.accmap['roth'] == len(accounttable)-1:
            output(("@%7s" * 3) % ("AftaTx", "fAftaTx", "tAftaTx"))
        output("\n")

    output("\nAccount Transactions Summary:\n\n")
    print_acc_header1()
    for year in range(S.numyr):
        #age = year + S.startage #### who's age??? NEED BOTH!!!!
        rmdref = [0,0]
        for j in range(2): # at most the first two accounts are type IRA w/ RMD requirement
            if accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref[j] = res.x[index_b(year,j)]/rmd 

        output("%3d:" % (year+S.startage))
        if S.accmap['IRA'] >1:
            output(("@%7.0f" * 6) % (
              res.x[index_b(year,0)]/1000.0, res.x[index_w(year,0)]/1000.0, rmdref[0]/1000.0, # IRA1
              res.x[index_b(year,1)]/1000.0, res.x[index_w(year,1)]/1000.0, rmdref[1]/1000.0)) # IRA2
        elif S.accmap['IRA'] == 1:
            output(("@%7.0f" * 3) % (
              res.x[index_b(year,0)]/1000.0, res.x[index_w(year,0)]/1000.0, rmdref[0]/1000.0)) # IRA1
        index = S.accmap['IRA']
        if S.accmap['roth'] >1:
            output(("@%7.0f" * 4) % (
              res.x[index_b(year,index)]/1000.0, res.x[index_w(year,index)]/1000.0, # roth1
              res.x[index_b(year,index+1)]/1000.0, res.x[index_w(year,index+1)]/1000.0)) # roth2
        elif S.accmap['roth'] == 1:
            output(("@%7.0f" * 2) % (
              res.x[index_b(year,index)]/1000.0, res.x[index_w(year,index)]/1000.0)) # roth1
        index = S.accmap['IRA'] + S.accmap['roth']
        #assert index == len(accounttable)-1
        if index == len(accounttable)-1:
            output(("@%7.0f" * 3) % (
                res.x[index_b(year,index)]/1000.0, res.x[index_w(year,index)]/1000.0, res.x[index_D(year)]/1000.0)) # aftertax account
        output("\n")
    print_acc_header1()

def print_tax(res):
    def printheader_tax():
        output("%s\n"%S.who)
        output((" age" + "@%7s" * 13) %
          ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "earlyP", "fedtax", "mTaxB%", "fAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble" ))
        output("\n")

    output("\nTax Summary:\n\n")
    printheader_tax()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        f = cg_taxable_fraction(year)
        ttax = tax + cg_tax +earlytax
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(accounttable)):
            withdrawal[accounttable[j]['acctype']] += res.x[index_w(year,j)]
        output(("%3d:" + "@%7.0f" * 13 ) %
              (year+S.startage, 
                withdrawal['IRA']/1000.0, # sum IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, earlytax/1000.0, tax/1000.0, rate*100, 
                withdrawal['aftertax']/1000.0, # sum Aftertax
              f*100, cg_tax/1000.0,
              ttax/1000.0, res.x[index_s(year)]/1000.0 ))
        output("\n")
    printheader_tax()

def print_tax_brackets(res):
    def printheader_tax_brackets():
        output("@@@@@@%46s" % "Marginal Rate(%):")
        for k in range(len(taxtable)):
            (cut, size, rate, base) = taxtable[k]
            output("@%6.0f" % (rate*100))
        output("\n")
        output("%s\n"%S.who)
        output((" age" + "@%7s" * 6) % ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "fedtax"))
        for k in range(len(taxtable)):
            output("@brckt%d" % k)
        output("@brkTot\n")

    output("\nOverall Tax Bracket Summary:\n")
    printheader_tax_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        output(("%3d:" + "@%7.0f" * 6 ) %
              (year+S.startage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0) )
        bt = 0
        for k in range(len(taxtable)):
            output("@%6.0f" % res.x[index_x(year,k)])
            bt += res.x[index_x(year,k)]
        output("@%6.0f\n" % bt)
    printheader_tax_brackets()

def print_cap_gains_brackets(res):
    def printheader_capgains_brackets():
        output("@@@@@%39s" % "Marginal Rate(%):")
        for l in range(len(capgainstable)):
            (cut, size, rate) = capgainstable[l]
            output("@%6.0f" % (rate*100))
        output("\n")
        output("%s\n"%S.who)
        output((" age" + "@%7s" * 5) % ("fAftaTx","cgTax%", "cgTaxbl", "T_inc", "cgTax"))
        for l in range(len(capgainstable)):
            output ("@brckt%d" % l)
        output ("@brkTot\n")

    output("\nOverall Capital Gains Bracket Summary:\n")
    printheader_capgains_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        f = 1
        atw = 0
        att = 0
        if S.accmap['aftertax'] > 0:
            f = cg_taxable_fraction(year)
            j = len(accounttable)-1 # Aftertax / investment account always the last entry when present
            atw = res.x[index_w(year,j)]/1000.0 # Aftertax / investment account
            att = (f*res.x[index_w(year,j)])/1000.0 # non-basis fraction / cg taxable $ 
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        output(("%3d:" + "@%7.0f" * 5 ) %
              (year+S.startage, 
              atw, # Aftertax / investment account
              f*100, att, # non-basis fraction / cg taxable $ 
              T/1000.0, cg_tax/1000.0))
        bt = 0
        bttax = 0
        for l in range(len(capgainstable)):
            ty = 0
            if S.accmap['aftertax'] > 0:
                ty = res.x[index_y(year,l)]
            output("@%6.0f" % ty)
            bt += ty
            bttax += ty * capgainstable[l][2]
        output("@%6.0f\n" % bt)
        if args.verbosewga:
            print(" cg bracket ttax %6.0f " % bttax, end='')
            print("x->y[1]: %6.0f "% (res.x[index_x(year,0)]+res.x[index_x(year,1)]),end='')
            print("x->y[2]: %6.0f "% (res.x[index_x(year,2)]+ res.x[index_x(year,3)]+ res.x[index_x(year,4)]+res.x[index_x(year,5)]),end='')
            print("x->y[3]: %6.0f"% res.x[index_x(year,6)])
        # TODO move to consistancy_check()
        #if (capgainstable[0][1]*i_mul -(res.x[index_x(year,0)]+res.x[index_x(year,1)])) <= res.x[index_y(year,1)]:
        #    print("y[1]remain: %6.0f "% (capgainstable[0][1]*i_mul -(res.x[index_x(year,0)]+res.x[index_x(year,1)])))
        #if (capgainstable[1][1]*i_mul - (res.x[index_x(year,2)]+ res.x[index_x(year,3)]+ res.x[index_x(year,4)]+res.x[index_x(year,5)])) <= res.x[index_y(year,2)]:
        #    print("y[2]remain: %6.0f " % (capgainstable[1][1]*i_mul - (res.x[index_x(year,2)]+ res.x[index_x(year,3)]+ res.x[index_x(year,4)]+res.x[index_x(year,5)])))
    printheader_capgains_brackets()

def print_constraint(row, b):
    print_model_row(row, True)
    print("<= b[]: %6.2f" % b)

def print_model_row(row, suppress_newline = False):
    for i in range(S.numyr):
        for k in range(len(taxtable)):
            if row[index_x(i, k)] != 0:
                print("x[%d,%d]: %6.3f" % (i, k, row[index_x(i, k)]),end=' ' )
    for i in range(S.numyr):
        for l in range(len(capgainstable)):
            if row[index_y(i, l)] != 0:
                print("y[%d,%d]: %6.3f " % (i, l, row[index_y(i, l)]),end=' ' )
    for i in range(S.numyr):
        for j in range(len(accounttable)):
            if row[index_w(i, j)] != 0:
                print("w[%d,%d]: %6.3f " % (i, j, row[index_w(i, j)]),end=' ' )
    for i in range(S.numyr+1): # b[] has an extra year
        for j in range(len(accounttable)):
            if row[index_b(i, j)] != 0:
                print("b[%d,%d]: %6.3f " % (i, j, row[index_b(i, j)]),end=' ' )
    for i in range(S.numyr):
        if row[index_s(i)] !=0:
            print("s[%d]: %6.3f " % (i, row[index_s(i)]),end=' ' )
    for i in range(S.numyr):
        if row[index_D(i)] !=0:
            print("D[%d]: %6.3f " % (i, row[index_D(i)]),end=' ' )
    if not suppress_newline:
        print()

def index_x(i, k):
    assert i>=0 and i < S.numyr
    assert k>=0 and k < len(taxtable)
    return i*len(taxtable)+k

def index_y(i,l):
    assert S.accmap['aftertax'] > 0
    assert i>=0 and i < S.numyr
    assert l>=0 and l < len(capgainstable)
    return tax_bracket_year + i*len(capgainstable)+l

def index_w(i,j):
    assert i>=0 and i < S.numyr
    assert j>=0 and j < len(accounttable)
    return tax_bracket_year+ capital_gains_bracket_year + i*len(accounttable)+j

def index_b(i,j):
    assert i>=0 and i < S.numyr+1 # b has an extra year on the end 
    assert j>=0 and j < len(accounttable)
    return tax_bracket_year+ capital_gains_bracket_year + withdrawal_accounts_year+i*len(accounttable)+j

def index_s(i):
    assert i>=0 and i < S.numyr
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + i

def index_D(i):
    assert S.accmap['aftertax'] > 0
    assert i>=0 and i < S.numyr
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + i

def cg_taxable_fraction(year):
    f = 1
    if S.accmap['aftertax'] > 0:
        for v in S.accounttable:
            if v['acctype'] == 'aftertax':
                f = 1 - (v['basis']/(v['bal']*v['rate']**year))
                break # should be the last entry anyway but...
    #f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
    return f

def OrdinaryTaxable(year):
    withdrawals = 0 
    for j in range(len(accounttable)):
        if accounttable[j]['acctype'] == 'IRA':
            withdrawals += res.x[index_w(year,j)]
    return withdrawals + S.taxed[year] + SS_taxable*S.SS[year] -(stded*S.i_rate**year)

def IncomeSummary(year):
    # TODO clean up and simplify this fuction
    #
    # return OrdinaryTaxable, Spendable, Tax, Rate, CG_Tax
    # Need to account for withdrawals from IRA deposited in Investment account NOT SPENDABLE
    age = year + S.startage
    earlytax = 0
    for j in range(len(accounttable)):
        if accounttable[j]['acctype'] != 'aftertax':
            if S.apply_early_penalty(year,accounttable[j]['mykey']):
                earlytax += res.x[index_w(year,j)]*penalty
    T = OrdinaryTaxable(year)
    cut, size, rate, base, brak_amount, sum_brackets = get_max_bracket(year, T, False)
    #tax = brak_amount * rate + base
    ntax = 0
    for k in range(len(taxtable)):
        ntax += res.x[index_x(year,k)]*taxtable[k][2]
    tax = ntax
    D = 0
    ncg_tax = 0
    if S.accmap['aftertax'] > 0:
        D =  res.x[index_D(year)]
        for l in range(len(capgainstable)):
            ncg_tax += res.x[index_y(year,l)]*capgainstable[l][2]
    tot_withdrawals = 0
    for j in range(len(accounttable)):
        tot_withdrawals += res.x[index_w(year,j)] 
    spendable = tot_withdrawals - D + S.income[year] + S.SS[year] - tax -ncg_tax - earlytax
    return T, spendable, tax, rate, ncg_tax, earlytax

def get_result_totals(res):
    twithd = 0 
    ttax = 0
    tcg_tax = 0
    tT = 0
    tearlytax = 0
    tincome = 0; pv_tincome = 0
    tspendable = 0
    pv_twithd = 0; pv_ttax = 0; pv_tT = 0
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        discountR = S.i_rate**-year # use rate of inflation as discount rate
        #age = year + S.startage
        #if age >= 70:
        #    rmd = RMD[age - 70]
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        tot_withdrawals = 0
        for j in range(len(accounttable)):
            tot_withdrawals += res.x[index_w(year,j)] 
        twithd += tot_withdrawals 
        tincome += S.income[year] + S.SS[year] # + withdrawals
        ttax += tax 
        tcg_tax += cg_tax 
        tearlytax += earlytax
        tT += T
        tspendable += spendable
    return twithd, tincome+twithd, tT, ttax, tcg_tax, tearlytax, tspendable

def print_base_config(res):
    totwithd, tincome, tTaxable, tincometax, tcg_tax, tearlytax, tspendable = get_result_totals(res)
    output("\n")
    output("Optimized for %s\n" % S.maximize)
    output('Minium desired: ${:0_.0f}\n'.format(S.desired[0]))
    output('Maximum desired: ${:0_.0f}\n'.format(S.max[0]))
    output('After tax yearly income: ${:0_.0f} adjusting for inflation\n'.format(res.x[index_s(0)]))
    output("\n")
    output('total withdrawals: ${:0_.0f}\n'.format(totwithd))
    output('total ordinary taxable income ${:_.0f}\n'.format(tTaxable))
    output('total ordinary tax on all taxable income: ${:0_.0f} ({:.1f}%) of taxable income\n'.format(tincometax+tearlytax, 100*(tincometax+tearlytax)/tTaxable))
    output('total income (withdrawals + other) ${:_.0f}\n'.format(tincome))
    output('total cap gains tax: ${:0_.0f}\n'.format(tcg_tax))
    output('total all tax on all income: ${:0_.0f} ({:.1f}%)\n'.format(tincometax+tcg_tax+tearlytax, 100*(tincometax+tcg_tax+tearlytax)/tincome))
    output("Total spendable (after tax money): ${:0_.0f}\n".format(tspendable))

# Program entry point
# Instantiate the parser
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true',
                    help="Extra output from solver")
parser.add_argument('-vt', '--verbosetax', action='store_true',
                    help="Output detailed tax info from solver")
parser.add_argument('-vtb', '--verbosetaxbrackets', action='store_true',
                    help="Output detailed tax bracket info from solver")
parser.add_argument('-vw', '--verbosewga', action='store_true',
                    help="Extra wga output from solver")
parser.add_argument('-vm', '--verbosemodel', action='store_true',
                    help="Output the binding constraints of the LP model")
parser.add_argument('-mall', '--verbosemodelall', action='store_true',
                    help="Output the entire LP model - not just the binding constraints")
parser.add_argument('-csv', '--csv', action='store_true',
                    help="Additionally write the output from to a csv file")
parser.add_argument('conffile')
args = parser.parse_args()

if args.csv:
    csv_file = open("a.csv", 'w')
else:
    csv_file = None

S = Data()
S.load_file(args.conffile)
accounttable = S.accounttable

print("\naccounttable: ", accounttable)

if args.verbosewga:
    print("accounttable: ", accounttable)

if args.verbosemodelall:
    non_binding_only = False
else:
    non_binding_only = True

tax_bracket_year = S.numyr * len(taxtable) # x[i,k]
capital_gains_bracket_year = 0 # no y[i,l] if no aftertax account
if S.accmap['aftertax'] > 0:
    capital_gains_bracket_year = S.numyr * len(capgainstable) # y[i,l]
withdrawal_accounts_year = S.numyr * len(accounttable) # w[i,j]
startbalance_accounts_year = (S.numyr+1) * len(accounttable) # b[i,j]
spendable_year = (S.numyr) # s[i]
investment_deposites_year = 0 # no D[i] if no aftertax account
if S.accmap['aftertax'] > 0:
    investment_deposites_year = (S.numyr) # D[i]

nvars = tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year

res = solve()
consistancy_check(res)

print_account_trans(res)
print_model_results(res)
if args.verbosetax:
    print_tax(res)
if args.verbosetaxbrackets:
    print_tax_brackets(res)
    print_cap_gains_brackets(res)
print_base_config(res)

if csv_file is not None:
    csv_file.close()