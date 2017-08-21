#!/usr/bin/python3

#
# A Retirement Planner (optimize withdrawals for most efficient use of the nest egg)
#

import toml
import argparse
import scipy.optimize
import re

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

accounttable = [] # array of [bal, rate, discount]
    # discount represents the value of the account balance (after a sort of tax)
    # The discount is approximently a cost of using the money in the account

# Required Minimal Distributions from IRA starting with age 70
RMD = [27.4, 26.5, 25.6, 24.7, 23.8, 22.9, 22.0, 21.2, 20.3, 19.5,  # age 70-79
       18.7, 17.9, 17.1, 16.3, 15.5, 14.8, 14.1, 13.4, 12.7, 12.0,  # age 80-89
       11.4, 10.8, 10.2,  9.6,  9.1,  8.6,  8.1,  7.6,  7.1,  6.7,  # age 90-99
        6.3,  5.9,  5.5,  5.2,  4.9,  4.5,  4.2,  3.9,  3.7,  3.4,  # age 100+
        3.1,  2.9,  2.6,  2.4,  2.1,  1.9,  1.9,  1.9,  1.9,  1.9]

cg_tax_rate = 0.15       # capital gains tax rate, overall estimate until I get brackets working
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
    def load_file(self, file):
        def startamount(amount, fra, start):
            if start > 70:
                start = 70
            if start < 62:
                start = 62
            if start < fra:
                return amount/(1.067**(fra-start))
            if start >= fra:
                return amount*(1.08**(start-fra))

        def create_SS_values (amount, fraage, agestr, bucket):
            firstage = agelist(agestr)
            #alter amount for start age vs fra (minus if before fra and + is after)
            amount = startamount(amount, fraage, next(firstage))
            for age in agelist(agestr):
                year = age - self.retireage
                if year < 0:
                    continue
                elif year >= self.numyr:
                    break
                else:
                    amount *= self.i_rate ** year
                    bucket[year] += amount

        self.accounttable = []
        with open(file) as conffile:
            d = toml.loads(conffile.read())
        
        self.maximize = d.get('maximize') # what to maximize for 
        if not 'maximize' in d:
            self.maximize = "Spending"

        self.i_rate = 1 + d.get('inflation', 0) / 100       # inflation rate: 2.5 -> 1.025
        self.r_rate = 1 + d.get('returns', 6) / 100         # invest rate: 6 -> 1.06

        self.startage = d['startage']
        self.endage = d.get('endage', max(96, self.startage+5))
        if 'prep' in d:
            self.workyr = d['prep']['workyears']
            self.maxsave = d['prep']['maxsave']
            self.worktax = 1 + d['prep'].get('tax_rate', 25)/100
        else:
            self.workyr = 0
        self.retireage = self.startage + self.workyr
        self.numyr = self.endage - self.retireage

        if 'SocialSecurity' in d:
            self.FRA = d['SocialSecurity']['FRA']
            self.FRAamount = d['SocialSecurity']['amount']
            self.SSage = d['SocialSecurity']['age']
            SS = [0] * self.numyr
            create_SS_values (self.FRAamount, self.FRA, self.SSage, SS)
            self.SS = SS 
        else:
            self.FRA = 67
            self.FRAamount = 0.0
            self.SSage = "67-"
            SS = [0] * self.numyr
            create_SS_values (self.FRAamount, self.FRA, self.SSage, SS)
            self.SS = SS 

        self.IRA = d.get('IRA', {'bal':0})
        if 'maxcontrib' not in self.IRA:
            self.IRA['maxcontrib'] = 18000 + 5500*2 # magic number move to better place TODO
        if 'rate' not in self.IRA:
            self.IRA['rate'] = self.r_rate 
        else:
            self.IRA['rate'] = 1 + self.IRA['rate'] / 100  # invest rate: 6 -> 1.06

        self.roth = d.get('roth', {'bal': 0});
        if 'maxcontrib' not in self.roth:
            self.roth['maxcontrib'] = 5500*2 # magic number fix TODO
        if 'rate' not in self.roth:
            self.roth['rate'] = self.r_rate 
        else:
            self.roth['rate'] = 1 + self.roth['rate'] / 100 # invest rate: 6 -> 1.06

        self.aftertax = d.get('aftertax', {'bal': 0})
        if 'basis' not in self.aftertax:
            self.aftertax['basis'] = 0
        if 'rate' not in self.aftertax:
            self.aftertax['rate'] = self.r_rate 
        else:
            self.aftertax['rate'] = 1 + self.aftertax['rate'] / 100 # invest rate: 6 -> 1.06

        self.accounttable+=[[self.IRA['bal'], self.IRA['rate'], 0.85]] 
        self.accounttable+=[[self.roth['bal'], self.roth['rate'], 1.0]]
        self.accounttable+=[[self.aftertax['bal'], self.aftertax['rate'], 0.90]]

        self.parse_expenses(d)
        self.sepp_end = max(5, 59-self.retireage)     # first year you can spend IRA reserved for SEPP
        self.sepp_ratio = 25                         # money per-year from SEPP  (bal/ratio)

    def parse_expenses(self, S):
        """ Return array of income/expense per year """
        def do_details(category, bucket, tax):
            for k,v in S.get(category, {}).items():
                for age in agelist(v['age']):
                    year = age - self.retireage
                    if year < 0:
                        continue
                    elif year >= self.numyr:
                        break
                    else:
                        amount = v['amount']
                        if v.get('inflation'):
                            amount *= self.i_rate ** year
                        bucket[year] += amount
                        if tax != 0 and v.get('tax'):
                            tax[year] += amount

        INC = [0] * self.numyr
        EXP = [0] * self.numyr
        TAX = [0] * self.numyr
        WANT = [0] * self.numyr
        MAX = [0] * self.numyr

        do_details("expense", EXP, 0)
        do_details("income", INC, TAX)
        do_details("desired", WANT, 0)
        do_details("max", MAX, 0)

        self.income = INC
        self.expenses = EXP
        self.taxed = TAX
        self.desired = WANT
        self.max = MAX

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
    # Adder objective function (R1') when PlusEstate is added
    #
    if S.maximize == "PlusEstate":
        pv_n = S.i_rate**(-S.numyr)
        for j in range(len(accounttable)):
            c[index_b(S.numyr,j)] = -1*accounttable[j][2] # account discount rate
        print("\nConstructing Spending + Estate Model:\n")
    else:
        print("\nConstructing Spending Model:\n")
        startamount = accounttable[0][0] +accounttable[1][0]+accounttable[2][0]
        balancer = 1/(startamount) 
        for j in range(len(accounttable)):
            c[index_b(S.numyr,j)] = -1*balancer *accounttable[j][2] # balance and discount rate
    
    #
    # Add constraint (2')
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(accounttable)):
            row[index_w(year,j)] = -1
        # NEXT 4 ROWS REPLACE TT1 and TT2
        for k in range(len(taxtable)): # was -1 but I think this is a bug so I removed it
            row[index_x(year,k)] = taxtable[k][2] # income tax
        p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row[index_w(year,2)] = cg_tax_rate*p-1 #  cap gains tax #over writes the -1 above
        # END REPLACE
        #row[index_Ft(year)] = 1
        #row[index_Fcg(year)] = 1
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
    # Add constrant (4') rows - TODO remove if [desired.income] is not defined in input
    #
    if S.desired[0] != 0:
        for year in range(1): #range(S.numyr):
            row = [0] * nvars
            row[index_s(year)] = -1
            A+=[row]
            b+=[ - S.desired[year] ]     # [- d_i]

    #
    # Add constraints for (5') rows - not added is [max.income] is not defined in input
    #
    if S.max[0] != 0:
        for year in range(1): #range(S.numyr):
            row = [0] * nvars
            row[index_s(year)] = 1
            A+=[row]
            b+=[ S.max[year] ]     # [ dm_i]

    #
    # Add constaints for (6') rows
    #
    for year in range(S.numyr):
        age = year + S.retireage
        if age >= 70:
            row = [0] * nvars
            rmd = RMD[age - 70]
            row[index_b(year,0)] = 1/rmd #Account 0 is TDRA
            row[index_w(year,0)] = -1
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
        row[index_w(year,0)] = -1 # Account 0 is TDRA
        A+=[row]
        b+=[S.income[year]+SS_taxable*S.SS[year]-stded*adj_inf]
    #
    # Add constraints for (7b')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        row[index_w(year,0)] = 1 # Account 0 is TDRA
        for k in range(len(taxtable)):
            row[index_x(year,k)] = -1
        A+=[row]
        b+=[stded*adj_inf-S.income[year]-SS_taxable*S.SS[year]]
    #
    # Add constraints for (8')
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)-1):
            row = [0] * nvars
            row[index_x(year,k)] = 1
            A+=[row]
            b+=[(taxtable[k][1])*(S.i_rate**year)] # inflation adjusted
    """
    #
    # Add constraints for (9a')
    #
    for year in range(S.numyr):
        #adj_inf = S.i_rate**year
        # Account Table 2 is aftertax 
        p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row = [0] * nvars
        for l in range(len(capgainstable)):
            row[index_y(year,l)] = 1
        row[index_w(year,2)] = -1*p # Account 2 is investment / stocks
        A+=[row]
        b+=[0]
    #
    # Add constraints for (9b')
    #
    for year in range(S.numyr):
        #adj_inf = S.i_rate**year
        p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row = [0] * nvars
        row[index_w(year,2)] = p # Account 2 is investment / stocks
        for l in range(len(capgainstable)):
            row[index_x(year,l)] = -1
        A+=[row]
        b+=[0]
    #
    # Add constraints for (10')
    #
    for year in range(S.numyr):
        for l in range(len(capgainstable)-1):
            row = [0] * nvars
            row[index_y(year,l)] = 1
            A+=[row]
            b+=[capgainstable[l][1]*(S.i_rate**year)] # inflation adjusted -mcg[i,k]

    #
    # Add constraints for (11')
    #
    #" " "
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        for l in range(len(capgainstable)-1):
            row = [0] * nvars
            row[index_y(year,l)] = 1
            row[index_w(year,1)] = 1
            A+=[row]
            b+=[capgainstable[l+1][0]*adj_inf -S.income[year]-SS_taxable*S.SS[year]+stded*adj_inf ] 
            """
    #
    # Add constraints for (12a')
    #
    for year in range(S.numyr): 
        for j in range(len(accounttable)-1): ### make -1 when adding 13a'
            row = [0] * nvars
            row[index_b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[index_b(year,j)] = -1*accounttable[j][1]
            row[index_w(year,j)] = accounttable[j][1]
            A+=[row]
            b+=[0]
    #
    # Add constraints for (12b')
    #
    for year in range(S.numyr):
        for j in range(len(accounttable)-1): ### make -1 when adding 13b'
            row = [0] * nvars
            row[index_b(year,j)] = accounttable[j][1]
            row[index_w(year,j)] = -1*accounttable[j][1]
            row[index_b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #
    # Add constraints for (13a')
    #
    for year in range(S.numyr): 
        j = 2 # nl the investment account
        row = [0] * nvars
        row[index_b(year+1,j)] = 1 ### b[i,j] supports an extra year
        row[index_b(year,j)] = -1*accounttable[j][1]
        row[index_w(year,j)] = accounttable[j][1]
        row[index_D(year)] = -1*accounttable[j][1]
        A+=[row]
        b+=[0]
    #
    # Add constraints for (13b')
    #
    # Not yet implemented
    for year in range(S.numyr):
        j = 2 # nl ==2 the investment account
        row = [0] * nvars
        row[index_b(year,j)] = accounttable[j][1]
        row[index_w(year,j)] = -1*accounttable[j][1]
        row[index_D(year)] = accounttable[j][1]
        row[index_b(year+1,j)] = -1  ### b[i,j] supports an extra year
        A+=[row]
        b+=[0]

    # Constraint for (14a')
    #   Set the begining b[1,j] balances
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = 1
        A+=[row]
        b+=[accounttable[j][0]]

    #
    # Constraint for (14b')
    #   Set the begining b[1,j] balances
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = -1
        A+=[row]
        b+=[-1*accounttable[j][0]]

    #
    # Constrant for (15') is default for sycpy so no code is needed
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
    if args.verbosewga:
        print_model_matrix(c, A, b, res.slack, non_binding_only)
        print(res)

    if res.success == False:
        print(res)
        exit(1)

    return res #res.x

def print_model_matrix(c, A, b, s, non_binding_only):
    if not non_binding_only:
        print("c: ")
        print_model_row(c)
        print()
        print("B? i: A_ub[i]: b[i]")
        for constraint in range(len(A)):
            #print(constraint, ":", A[constraint], b[constraint])
            if s[constraint] >0:
                print("  ", end='')
            else:
                print("B ", end='')
            print(constraint, ": ", sep='', end='')
            print_constraint( A[constraint], b[constraint])
            #print()
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
    def check_row_consecutive(row):
        for i in range(len(row)-1):
            if row[i] +1 != row[i+1]:
                print("Check_row_consecutive: failed, row[%d](%d) != row[%d](%d)" % (i, row[i], i+1, row[i+1]))
    def do_write_x():
        ky = 0
        row = [0] * nvars
        for i in range(S.numyr):
            for k in range(len(taxtable)):
                row[index_x(i, k)] = ky
                ky+=1
        for i in range(S.numyr):
            for l in range(len(capgainstable)):
                row[index_y(i, l)] = ky
                ky+=1
        for i in range(S.numyr):
            for j in range(len(accounttable)):
                row[index_w(i, j)] = ky
                ky+=1
        for i in range(S.numyr+1): # b[] has an extra year
            for j in range(len(accounttable)):
                row[index_b(i, j)] = ky
                ky+=1
        for i in range(S.numyr):
            row[index_s(i)] = ky
            ky+=1
        for i in range(S.numyr):
            row[index_D(i)] = ky
            ky+=1
        for i in range(S.numyr):
            row[index_Ft(i)] = ky
            ky+=1
        for i in range(S.numyr):
            row[index_Fcg(i)] = ky
            ky+=1
        check_row_consecutive(row)
    # check to see if the ordinary tax brackets are filled in properly
    print()
    print()
    print("Consistancy Checking:")
    print()
    #Quik check indexes:
    if index_x(0,0) != 0:
        print("Index Error: x(0,0) != 0 it is: %d" % index(0,0))
    if index_x(S.numyr-1,len(taxtable)-1)+1 != index_y(0,0):
        print("Index Error: index_x(S.numyr, len(taxtable)-1)+1 != index_y(0,0)")
        print("\tx():", index_x(S.numyr-1,len(taxtable)-1))
        print("\ty():", index_y(0,0))
    if index_y(S.numyr-1,len(capgainstable)-1)+1 != index_w(0,0):
        print("Index Error: index_y(S.numyr-1, len(capgainstable)-1)+1 != index_w(0,0)")
        print("\ty():", index_y(S.numyr-1,len(capgainstable)-1))
        print("\tw():", index_w(0,0))
    if index_w(S.numyr-1,len(accounttable)-1)+1 != index_b(0,0):
        print("Index Error: index_w(S.numyr-1, len(accounttable)-1)+1 != index_b(0,0)")
        print("\tw():", index_w(S.numyr-1,len(accounttable)-1))
        print("\tb():", index_b(0,0))
    if index_b(S.numyr,len(accounttable)-1)+1 != index_s(0): # has years+1
        print("Index Error: index_b(S.numyr-1, len(accounttable)-1)+1 != index_s(0)")
        print("\tb():", index_b(S.numyr-1,len(accounttable)-1))
        print("\ts():", index_s(0))
    if index_s(S.numyr-1)+1 != index_D(0): # has years+1
        print("Index Error: Expect index_s(S.numyr -1)+1 to equal index_D(0)")
        print("\ts(S.numyr-1):", index_s(S.numyr-1))
        print("\tD(S.numyr-1):", index_D(0))
    if index_D(S.numyr-1)+1 != index_Ft(0): # has years+1
        print("Index Error: Expect index_D(S.numyr -1)+1 to equal index_Ft(0)")
        print("\ts(S.numyr-1):", index_D(S.numyr-1))
        print("\tD(S.numyr-1):", index_Ft(0))
    if index_Ft(S.numyr-1)+1 != index_Fcg(0): # has years+1
        print("Index Error: Expect index_Ft(S.numyr -1)+1 to equal index_Fcg(0)")
        print("\ts(S.numyr-1):", index_Ft(S.numyr-1))
        print("\tD(S.numyr-1):", index_Fcg(0))
    if nvars-1 != index_Fcg(S.numyr-1):
        print("Index Error: Expect (nvars -1) to equal Fcg(S.numyr-1)")
        print("\tvnars -1:", nvars-1)
        print("\tFcg(S.numyr-1):", index_Fcg(S.numyr-1))
    # write a res.x vector from 1-nvars
    if args.verbosewga:
        do_write_x()

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
        #TaxableOrdinary = res.x[index_w(year,0)] + S.income[year] -stded*i_mul
        TaxableOrdinary = OrdinaryTaxable(year)
        if (TaxableOrdinary + 0.1 < s) or (TaxableOrdinary - 0.1 > s):
            print("Error: Expected Taxable Ordinary income %6.2f doesn't match bracket sum %6.2f" % (TaxableOrdinary,s))

        for j in range(len(accounttable)-1):
            if res.x[index_b(year+1,j)] -( res.x[index_b(year,j)] - res.x[index_w(year,j)])*accounttable[0][1]>1:
                print("account[%d] year to year balance NOT OK years %d to %d" % (j, year, year+1))
        if res.x[index_b(year+1,2)] -( res.x[index_b(year,2)] - res.x[index_w(year,2)] + res.x[index_D(year)])*accounttable[0][1]>1:
            print("account[%d] year to year balance NOT OK years %d to %d" % (2, year, year+1))

        T,spendable,tax,rate,cg_tax = IncomeSummary(year)
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

def print_model_results(res):
    def printheader1():
        print((" age" + " %7s" * 13) %
          ("IRA", "fIRA", "RMDref", "Roth", "fRoth", "AftaTx", "fAftaTx", "tAftaTx", "o_inc", "SS", "Spndble", "TFedTax", "Desired"))

    twithd = 0 
    ttax = 0
    tT = 0
    pv_twithd = 0; pv_ttax = 0; pv_tT = 0
    printheader1()
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        discountR = S.i_rate**-year # use rate of inflation as discount rate
        age = year + S.retireage
        if age >= 70:
            rmd = RMD[age - 70]
        T,spendable,tax,rate,cg_tax = IncomeSummary(year)
        if age >= 70:
            rmdref = res.x[index_b(year,0)]/rmd 
        else:
            rmdref = 0

        print(("%3d:" + " %7.0f" * 13 ) %
              (year+S.retireage, 
              res.x[index_b(year,0)]/1000.0, res.x[index_w(year,0)]/1000.0, rmdref/1000.0, # IRA
              res.x[index_b(year,1)]/1000.0, res.x[index_w(year,1)]/1000.0, # Roth
              res.x[index_b(year,2)]/1000.0, res.x[index_w(year,2)]/1000.0, res.x[index_D(year)]/1000.0, # AftaTax
              S.income[year]/1000.0, S.SS[year]/1000.0,
              #T/1000.0, tax/1000.0, rate*100, 
              res.x[index_s(year)]/1000.0, (tax+cg_tax)/1000.0, S.desired[year]/1000.0))
        twithd += res.x[index_w(year,0)] + res.x[index_w(year,1)] +res.x[index_w(year,2)]
        ttax += tax + cg_tax # includes both ordinary income and cap gains tax
        tT += T
        pv_twithd += (res.x[index_w(year,0)] + res.x[index_w(year,1)] )* discountR
        pv_ttax += tax *discountR
        pv_tT += T*discountR

    year = S.numyr
    print(("%3d:" + " %7.0f %7s %7s" + " %7.0f %7s" * 2 + " %7s" * 5) %
        (year+S.retireage, 
        res.x[index_b(year,0)]/1000.0, '-', '-',  # res.x[index_w(year,0)]/1000.0, # IRA
        res.x[index_b(year,1)]/1000.0, '-', # res.x[index_w(year,1)]/1000.0, # Roth
        res.x[index_b(year,2)]/1000.0, '-', # res.x[index_w(year,2)]/1000.0, # AftaTax
        '-', '-', '-', '-', '-'))
        #S.income[year]/1000.0, T/1000.0, tax/1000.0, rate*100, rmdref/1000.0, 
        #S.desired[year]/1000.0))
    printheader1()
    # ${:0,.2f}
    print('\ntotal withdrawals: ${:0,.0f}, total ordinary taxable income ${:,.0f}'.format(twithd, tT))
    print('total ordinary tax on all income: ${:0,.0f} ({:.1f}%)'.format(ttax, 100*ttax/tT))
    print('\ntotal cap gains tax ??? on all income: ${:0,.0f} ({:.1f}%)'.format(ttax, 100*ttax/tT))
    print('total all tax ??? on all income: ${:0,.0f} ({:.1f}%)'.format(ttax, 100*ttax/tT))

    print('\ntotal pv withdrawals: ${:0,.0f}, total pv income ${:0,.0f}'.format(pv_twithd, pv_tT))
    print('total pv tax on all income: ${:0,.0f} ({:.1f}%)'.format(pv_ttax, 100*ttax/tT))

def print_tax(res):
    def printheader_tax():
        print((" age" + " %7s" * 12) %
          ("fIRA", "o_inc", "TxbleSS", "deduct", "T_inc", "fedtax", "mTaxB%", "fAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble" ))
    print("\n\nOverall Tax Report:\n")
    printheader_tax()
    for year in range(S.numyr):
        age = year + S.retireage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax = IncomeSummary(year)
        p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        ttax = tax + cg_tax
        #totaftataxWith += res.x[index_w(year,2)] # AftaTax
        print(("%3d:" + " %7.0f" * 12 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.income[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0, rate*100, 
              res.x[index_w(year,2)]/1000.0, # AftaTax
              p*100, cg_tax/1000.0,
              ttax/1000.0, res.x[index_s(year)]/1000.0 ))

    printheader_tax()

def print_tax_brackets(res):
    def printheader_tax_brackets():
        print("%52s" % "Marginal Rate(%):", end='')
        for k in range(len(taxtable)):
            (cut, size, rate, base) = taxtable[k]
            print(" %6.0f" % (rate*100), end='')
        print()
        print((" age" + " %7s" * 6) % ("fIRA", "o_inc", "txblSS", "deduct", "T_inc", "fedtax"), end=' ')
        for k in range(len(taxtable)):
            print ("brckt%d" % k, sep='', end=' ')
        print ("brkTot", sep='')

    print("\n\nOverall Tax Bracket Report:\n")
    printheader_tax_brackets()
    for year in range(S.numyr):
        age = year + S.retireage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax = IncomeSummary(year)
        ttax = tax + cg_tax
        print(("%3d:" + " %7.0f" * 6 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.income[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0), 
              end='')
        bt = 0
        for k in range(len(taxtable)):
            print(" %6.0f" % res.x[index_x(year,k)], end='')
            bt += res.x[index_x(year,k)]
        print(" %6.0f" % bt)
    printheader_tax_brackets()

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
    for i in range(S.numyr):
        if row[index_Ft(i)] !=0:
            print("Ft[%d]: %6.3f " % (i, row[index_Ft(i)]),end=' ' )
    for i in range(S.numyr):
        if row[index_Fcg(i)] !=0:
            print("Fct[%d]: %6.3f " % (i, row[index_Fcg(i)]),end=' ' )
    if not suppress_newline:
        print()

def index_x(i, k):
    assert i>=0 and i < S.numyr
    assert k>=0 and k < len(taxtable)
    return i*len(taxtable)+k

def index_y(i,l):
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
    assert i>=0 and i < S.numyr
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + i

def index_Ft(i):
    assert i>=0 and i < S.numyr
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year + i

def index_Fcg(i):
    assert i>=0 and i < S.numyr
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year + income_tax_year + i

def OrdinaryTaxable(year):
    return res.x[index_w(year,0)] + S.income[year] + SS_taxable*S.SS[year] -(stded*S.i_rate**year)

def IncomeSummary(year):
    # return OrdinaryTaxable, Spendable, Tax, Rate, CG_Tax
    # Need to account for withdrawals from IRA deposited in Investment account NOT SPENDABLE
    T = OrdinaryTaxable(year)
    cut, size, rate, base, brak_amount, sum_brackets = get_max_bracket(year, T, False)
    tax = brak_amount * rate + base
    p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
    cg_tax = res.x[index_w(year,2)] *p *cg_tax_rate 
    spendable = res.x[index_w(year,0)] + res.x[index_w(year,1)] + res.x[index_w(year,2)] - res.x[index_D(year)] + S.income[year] + S.SS[year] - tax -cg_tax
    return T, spendable, tax, rate, cg_tax

def print_base_config(res):
    print()
    print("Optimized for %s" % S.maximize)
    print('Minium desired: ${:0,.0f}'.format(S.desired[0]))
    #print('total pv tax on all income: ${:0,.0f} ({:.1f}%)'.format(pv_ttax, 100*ttax/tT))
    print('Maximum desired: ${:0,.0f}'.format(S.max[0]))
    print('Projected yearly income: ${:0,.0f}'.format(res.x[index_s(0)]))
    print()

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
parser.add_argument('-mall', '--verbosemodelall', action='store_true',
                    help="Extra wga output from solver")
parser.add_argument('conffile')
args = parser.parse_args()

S = Data()
S.load_file(args.conffile)
accounttable = S.accounttable
if args.verbosewga:
    print("accounttable: ", accounttable)

if args.verbosemodelall:
    non_binding_only = False
else:
    non_binding_only = True


tax_bracket_year = S.numyr * len(taxtable) # x[i,k]
capital_gains_bracket_year = S.numyr * len(capgainstable) # y[i,l]
withdrawal_accounts_year = S.numyr * len(accounttable) # w[i,j]
startbalance_accounts_year = (S.numyr+1) * len(accounttable) # b[i,j]
spendable_year = (S.numyr) # s[i]
investment_deposites_year = (S.numyr) # D[i]
income_tax_year = S.numyr # Ft[i]
cap_gains_tax_year = S.numyr # Fcg[i]

nvars = tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year + income_tax_year + cap_gains_tax_year

res = solve()
consistancy_check(res)
print_model_results(res)
if args.verbosetax:
    print_tax(res)
if args.verbosetaxbrackets:
    print_tax_brackets(res)
print_base_config(res)
