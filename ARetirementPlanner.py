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
    def load_file(self, file):

        self.accounttable = []
        with open(file) as conffile:
            d = toml.loads(conffile.read())
        
        self.retirement_type = d.get('retirement_type') # what to maximize for 
        if not 'retirement_type' in d:
            self.retirement_type = 'joint'

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

        self.IRA = d.get('IRA', {'bal':0})
        print(self.IRA)
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

        # TODO find a good place for the following three magic numbers (0.85, 1.0, 0.90)
        self.accounttable+=[[self.IRA['bal'], self.IRA['rate'], 0.85]] 
        self.accounttable+=[[self.roth['bal'], self.roth['rate'], 1.0]]
        self.accounttable+=[[self.aftertax['bal'], self.aftertax['rate'], 0.90]]

        self.SSinput = [{}, {}] 
        self.parse_expenses(d)

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
            for k,v in S.get( 'SocialSecurity' , {}).items():
                sections += 1
                print("key: ", k, ", value: ", v)
                fraamount = v['amount']
                fraage = v['FRA']
                agestr = v['age']
                if fraamount < 0 and sections == 1:
                    self.SSinput[1] = {'key': k, 'amount': fraamount, 'fra': fraage, 'agestr': agestr}
                else:
                    self.SSinput[index] = {'key': k, 'amount': fraamount, 'fra': fraage, 'agestr': agestr}
                    index += 1

            for i in range(sections):
                print("SSinput", self.SSinput)
                agestr = self.SSinput[i]['agestr']
                firstage = agelist(agestr)
                disperseage = next(firstage)
                fraage = self.SSinput[i]['fra']
                fraamount = self.SSinput[i]['amount']
                if fraamount < 0:
                    assert i == 1
                    fraamount = self.SSinput[0]['amount']/2 # TODO check to verify the startamount() is correct for this case
                    # alter amount for start age vs fra (minus if before fra and + is after)
                    amount = startamount(fraamount, fraage, min(disperseage,fraage))
                else:
                    # alter amount for start age vs fra (minus if before fra and + is after)
                    amount = startamount(fraamount, fraage, disperseage)
                print("FRA: %d, FRAamount: %6.0f, Age: %s, amount: %6.0f" % (fraage, fraamount, agestr, amount))
                for age in agelist(agestr):
                    year = age - self.retireage
                    if year < 0:
                        continue
                    elif year >= self.numyr:
                        break
                    else:
                        adj_amount = amount * self.i_rate ** year
                        print("age %d, year %d, bucket: %6.0f += amount %6.0f" %(age, year, bucket[year], adj_amount))
                        bucket[year] += adj_amount
            #if self.retirement_type == 'joint' and section == 1:
            #    print("NEED TO IMPLEMENT DEFAULT SS FOR SPOUCE")

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
            c[index_b(S.numyr,j)] = -1*accounttable[j][2] # account discount rate
        print("\nConstructing Spending + Estate Model:\n")
    else:
        print("\nConstructing Spending Model:\n")
        startamount = accounttable[0][0] +accounttable[1][0]+accounttable[2][0]
        balancer = 1/(startamount) 
        for j in range(len(accounttable)):
            c[index_b(S.numyr,j)] = -1*balancer *accounttable[j][2] # balance and discount rate
    
    """
    #
    # Add constraint (2' as imp)
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(accounttable)-1):
            age = year + S.retireage
            if age < 60:
                p = 1-penalty
            else:
                p = 1
            row[index_w(year,j)] = -1*p 
        for k in range(len(taxtable)): 
            row[index_x(year,k)] = taxtable[k][2] # income tax
        f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row[index_w(year,2)] = cg_tax_rate*f-1 #  cap gains tax #over writes the -1 above
        row[index_D(year)] = 1
        row[index_s(year)] = 1
        A+=[row]
        b+=[S.income[year] + S.SS[year]]
    """
    #
    # Add constraint (2')
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(accounttable)-1):
            age = year + S.retireage
            if age < 60:
                p = 1-penalty
            else:
                p = 1
            row[index_w(year,j)] = -1*p 
        row[index_w(year,2)] = -1 
        for k in range(len(taxtable)): 
            row[index_x(year,k)] = taxtable[k][2] # income tax
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
        b+=[S.taxed[year]+SS_taxable*S.SS[year]-stded*adj_inf]
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
    for year in range(S.numyr):
        f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row = [0] * nvars
        for l in range(len(capgainstable)):
            row[index_y(year,l)] = 1
        row[index_w(year,2)] = -1*f # Account 2 is investment / stocks
        A+=[row]
        b+=[0]
    #
    # Add constraints for (9b')
    #
    for year in range(S.numyr):
        f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        row = [0] * nvars
        row[index_w(year,2)] = f # Account 2 is investment / stocks
        for l in range(len(capgainstable)):
            row[index_y(year,l)] = -1
        A+=[row]
        b+=[0]
    #
    # Add constraints for (10')
    #
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
    for year in range(S.numyr): 
        for j in range(len(accounttable)-1): 
            row = [0] * nvars
            row[index_b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[index_b(year,j)] = -1*accounttable[j][1]
            row[index_w(year,j)] = accounttable[j][1]
            A+=[row]
            b+=[0]
    #
    # Add constraints for (11b')
    #
    for year in range(S.numyr):
        for j in range(len(accounttable)-1): 
            row = [0] * nvars
            row[index_b(year,j)] = accounttable[j][1]
            row[index_w(year,j)] = -1*accounttable[j][1]
            row[index_b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #
    # Add constraints for (12a')
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
    # Add constraints for (12b')
    #
    for year in range(S.numyr):
        j = 2 # nl ==2 the investment account
        row = [0] * nvars
        row[index_b(year,j)] = accounttable[j][1]
        row[index_w(year,j)] = -1*accounttable[j][1]
        row[index_D(year)] = accounttable[j][1]
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
        b+=[accounttable[j][0]]
    #
    # Constraint for (13b')
    #   Set the begining b[1,j] balances
    #
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = -1
        A+=[row]
        b+=[-1*accounttable[j][0]]
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
    if args.verbosewga:
        print_model_matrix(c, A, b, res.slack, non_binding_only)
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
            for l in range(len(capgainstable)):
                row[index_ns(i,l)] = ky
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
    if index_D(S.numyr-1)+1 != index_ns(0,0): # has years+1
        print("Index Error: Expect index_D(S.numyr -1)+1 to equal index_ns(0,0)")
        print("\tD(S.numyr-1):", index_D(S.numyr-1))
        print("\tns(0,0):", index_ns(0,0))
    if nvars-1 != index_ns(S.numyr-1, len(capgainstable)-2):
        print("Index Error: Expect (nvars -1) to equal ns(S.numyr-1,len(capgainstable)-1)")
        print("\tvnars -1:", nvars-1)
        print("\tns(S.numyr-1,len(capgainstable)-1):", index_ns(S.numyr-1, len(capgainstable)-1))
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

def print_model_results(res, csvf):
    def printheader1():
        print((" age" + " %7s" * 12) %
          ("IRA", "fIRA", "RMDref", "Roth", "fRoth", "AftaTx", "fAftaTx", "tAftaTx", "o_inc", "SS", "TFedTax", "Spndble"))
        if csvf is not None:
            csvf.write(("age" + ",%7s" * 12) % ("IRA", "fIRA", "RMDref", "Roth", "fRoth", "AftaTx", "fAftaTx", "tAftaTx", "o_inc", "SS", "TFedTax", "Spndble"))
            csvf.write("\n")

    print("\nActivity Summary:\n")
    if csvf is not None:
        csvf.write("\nActivity Summary:\n")
        csvf.write('\n')
    printheader1()
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        age = year + S.retireage
        if age >= 70:
            rmd = RMD[age - 70]
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        if age >= 70:
            rmdref = res.x[index_b(year,0)]/rmd 
        else:
            rmdref = 0

        print(("%3d:" + " %7.0f" * 12 ) %
              (year+S.retireage, 
              res.x[index_b(year,0)]/1000.0, res.x[index_w(year,0)]/1000.0, rmdref/1000.0, # IRA
              res.x[index_b(year,1)]/1000.0, res.x[index_w(year,1)]/1000.0, # Roth
              res.x[index_b(year,2)]/1000.0, res.x[index_w(year,2)]/1000.0, res.x[index_D(year)]/1000.0, # AftaTax
              S.income[year]/1000.0, S.SS[year]/1000.0,
              (tax+cg_tax+earlytax)/1000.0, res.x[index_s(year)]/1000.0) )
        if csvf is not None:
            csvf.write(("%3d:" + ",%7.0f" * 12 ) %
              (year+S.retireage, 
              res.x[index_b(year,0)], res.x[index_w(year,0)], rmdref, # IRA
              res.x[index_b(year,1)], res.x[index_w(year,1)], # Roth
              res.x[index_b(year,2)], res.x[index_w(year,2)], res.x[index_D(year)], # AftaTax
              S.income[year], S.SS[year],
              (tax+cg_tax+earlytax), res.x[index_s(year)]) )
            csvf.write('\n')

    year = S.numyr
    print(("%3d:" + " %7.0f %7s %7s" + " %7.0f %7s" * 2 + " %7s" * 5) %
        (year+S.retireage, 
        res.x[index_b(year,0)], '-', '-',  # res.x[index_w(year,0)]/1000.0, # IRA
        res.x[index_b(year,1)], '-', # res.x[index_w(year,1)]/1000.0, # Roth
        res.x[index_b(year,2)], '-', # res.x[index_w(year,2)]/1000.0, # AftaTax
        '-', '-', '-', '-', '-'))
    if csvf is not None:
        csvf.write(("%3d:" + ",%7.0f,%7s,%7s" + ",%7.0f,%7s" * 2 + ",%7s" * 5) %
        (year+S.retireage, 
        res.x[index_b(year,0)], '-', '-',  # res.x[index_w(year,0)]/1000.0, # IRA
        res.x[index_b(year,1)], '-', # res.x[index_w(year,1)]/1000.0, # Roth
        res.x[index_b(year,2)], '-', # res.x[index_w(year,2)]/1000.0, # AftaTax
        '-', '-', '-', '-', '-'))
        csvf.write('\n')
    printheader1()

def print_tax(res, csvf):
    def printheader_tax():
        print((" age" + " %7s" * 13) %
          ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "earlyP", "fedtax", "mTaxB%", "fAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble" ))
        if csvf is not None:
            csvf.write(("age" + ",%7s" * 13) %
            ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "earlyP", "fedtax", "mTaxB%", "fAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble" ))
            csvf.write("\n")

    print("\nTax Summary:\n")
    if csvf is not None:
        csvf.write("\nTax Summary:\n")
        csvf.write("\n")
    printheader_tax()
    for year in range(S.numyr):
        age = year + S.retireage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        ttax = tax + cg_tax +earlytax
        print(("%3d:" + " %7.0f" * 13 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, earlytax/1000.0, tax/1000.0, rate*100, 
              res.x[index_w(year,2)]/1000.0, # AftaTax
              f*100, cg_tax/1000.0,
              ttax/1000.0, res.x[index_s(year)]/1000.0 ))
        if csvf is not None:
            csvf.write(("%3d:" + ",%7.0f" * 13 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)], # IRA
              S.taxed[year], SS_taxable*S.SS[year],
              stded*i_mul, T, earlytax, tax, rate*100, 
              res.x[index_w(year,2)], # AftaTax
              f*100, cg_tax,
              ttax, res.x[index_s(year)] ))
            csvf.write("\n")

    printheader_tax()

def print_tax_brackets(res, csvf):
    def printheader_tax_brackets():
        print("%52s" % "Marginal Rate(%):", end='')
        for k in range(len(taxtable)):
            (cut, size, rate, base) = taxtable[k]
            print(" %6.0f" % (rate*100), end='')
        print()
        print((" age" + " %7s" * 6) % ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "fedtax"), end=' ')
        for k in range(len(taxtable)):
            print ("brckt%d" % k, sep='', end=' ')
        print ("brkTot", sep='')
        if csvf is not None:
            csvf.write(",,,,,,%s" % "Marginal Rate(%):")
            for k in range(len(taxtable)):
                (cut, size, rate, base) = taxtable[k]
                csvf.write(",%6.0f" % (rate*100))
            csvf.write("\n")
            csvf.write(("age" + ",%7s" * 6) % ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "fedtax"))
            for k in range(len(taxtable)):
                csvf.write(",brckt%d" % k)
            csvf.write(",brkTot\n")

    print("\nOverall Tax Bracket Summary:\n")
    if csvf is not None:
        csvf.write("\nOverall Tax Bracket Summary:\n")
        csvf.write("\n")
    printheader_tax_brackets()
    for year in range(S.numyr):
        age = year + S.retireage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        print(("%3d:" + " %7.0f" * 6 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0), 
              end='')
        if csvf is not None:
            csvf.write(("%3d:" + ",%7.0f" * 6 ) %
              (year+S.retireage, 
              res.x[index_w(year,0)]/1000.0, # IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0))
        bt = 0
        for k in range(len(taxtable)):
            print(" %6.0f" % res.x[index_x(year,k)], end='')
            if csvf is not None:
                csvf.write(",%6.0f" % res.x[index_x(year,k)])
            bt += res.x[index_x(year,k)]
        print(" %6.0f" % bt)
        if csvf is not None:
            csvf.write(",%6.0f\n" % bt)
    printheader_tax_brackets()

def print_cap_gains_brackets(res, csvf):
    def printheader_capgains_brackets():
        print("%44s" % "Marginal Rate(%):", end='')
        for l in range(len(capgainstable)):
            (cut, size, rate) = capgainstable[l]
            print(" %6.0f" % (rate*100), end='')
        print()
        print((" age" + " %7s" * 5) % ("fAftaTx","cgTax%", "cgTaxbl", "T_inc", "cgTax"), end=' ')
        for l in range(len(capgainstable)):
            print ("brckt%d" % l, sep='', end=' ')
        print ("brkTot", sep='')
        if csvf is not None:
            csvf.write(",,,,,,%s" % "Marginal Rate(%):")
            for l in range(len(capgainstable)):
                (cut, size, rate) = capgainstable[l]
                csvf.write(",%6.0f" % (rate*100))
            csvf.write("\n")
            csvf.write(("age" + ",%7s" * 5) % ("fAftaTx","cgTax%", "cgTaxbl", "T_inc", "cgTax"))
            for l in range(len(capgainstable)):
                csvf.write (",brckt%d" % l)
            csvf.write (",brkTot\n")

    print("\nOverall Capital Gains Bracket Summary:\n")
    if csvf is not None:
        csvf.write("\nOverall Capital Gains Bracket Summary:\n")
        csvf.write ("\n")
    printheader_capgains_brackets()
    for year in range(S.numyr):
        age = year + S.retireage
        i_mul = S.i_rate ** year
        f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        print(("%3d:" + " %7.0f" * 5 ) %
              (year+S.retireage, 
              res.x[index_w(year,2)]/1000.0, # Aftertax / investment account
              f*100, (f*res.x[index_w(year,2)])/1000.0, # non-basis fraction / cg taxable $ 
              T/1000.0, cg_tax/1000.0), 
              end='')
        if csvf is not None:
            csvf.write(("%3d:" + ",%7.0f" * 5 ) %
              (year+S.retireage, 
              res.x[index_w(year,2)]/1000.0, # Aftertax / investment account
              f*100, (f*res.x[index_w(year,2)])/1000.0, # non-basis fraction / cg taxable $ 
              T/1000.0, cg_tax/1000.0))
        bt = 0
        bttax = 0
        for l in range(len(capgainstable)):
            print(" %6.0f" % res.x[index_y(year,l)], end='')
            if csvf is not None:
                csvf.write(",%6.0f" % res.x[index_y(year,l)])
            bt += res.x[index_y(year,l)]
            bttax += res.x[index_y(year,l)] * capgainstable[l][2]
        print(" %6.0f" % bt)
        if csvf is not None:
            csvf.write(",%6.0f\n" % bt)
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
    for i in range(S.numyr):
        for l in range(len(capgainstable)-1):
            if row[index_ns(i,l)] !=0:
                print("ns[%d,%d]: %6.3f " % (i,l, row[index_ns(i,l)]),end=' ' )
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

def index_ns(i,l):
    assert i>=0 and i < S.numyr
    assert l>=0 and l < len(capgainstable)-1
    return tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year + i*(len(capgainstable)-1)+l

def OrdinaryTaxable(year):
    return res.x[index_w(year,0)] + S.taxed[year] + SS_taxable*S.SS[year] -(stded*S.i_rate**year)

def IncomeSummary(year):
    # TODO clean up and simplify this fuction
    #
    # return OrdinaryTaxable, Spendable, Tax, Rate, CG_Tax
    # Need to account for withdrawals from IRA deposited in Investment account NOT SPENDABLE
    age = year + S.retireage
    if age < 60:
        earlytax = res.x[index_w(year,0)]*penalty + res.x[index_w(year,1)]*penalty
    else:
        earlytax = 0
    T = OrdinaryTaxable(year)
    cut, size, rate, base, brak_amount, sum_brackets = get_max_bracket(year, T, False)
    #tax = brak_amount * rate + base
    ntax = 0
    for k in range(len(taxtable)):
        ntax += res.x[index_x(year,k)]*taxtable[k][2]
    tax = ntax
    p = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
    ncg_tax = 0
    for l in range(len(capgainstable)):
        ncg_tax += res.x[index_y(year,l)]*capgainstable[l][2]
    spendable = res.x[index_w(year,0)] + res.x[index_w(year,1)] + res.x[index_w(year,2)] - res.x[index_D(year)] + S.income[year] + S.SS[year] - tax -ncg_tax - earlytax
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
        age = year + S.retireage
        if age >= 70:
            rmd = RMD[age - 70]
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        twithd += res.x[index_w(year,0)] + res.x[index_w(year,1)] +res.x[index_w(year,2)]
        tincome += S.income[year] + S.SS[year] # + withdrawals
        ttax += tax 
        tcg_tax += cg_tax 
        tearlytax += earlytax
        tT += T
        pv_twithd += (res.x[index_w(year,0)] + res.x[index_w(year,1)] )* discountR
        pv_ttax += tax *discountR
        pv_tT += T*discountR
        tspendable += spendable
    return twithd, tincome+twithd, tT, ttax, tcg_tax, tearlytax, tspendable

def print_base_config(res, csvf):
    totwithd, tincome, tTaxable, tincometax, tcg_tax, tearlytax, tspendable = get_result_totals(res)
    print()
    print("Optimized for %s" % S.maximize)
    print('Minium desired: ${:0,.0f}'.format(S.desired[0]))
    print('Maximum desired: ${:0,.0f}'.format(S.max[0]))
    print('After tax yearly income: ${:0,.0f} adjusting for inflation'.format(res.x[index_s(0)]))
    print()
    print('total withdrawals: ${:0,.0f}'.format(totwithd))
    print('total ordinary taxable income ${:,.0f}'.format(tTaxable))
    print('total ordinary tax on all taxable income: ${:0,.0f} ({:.1f}%) of taxable income'.format(tincometax+tearlytax, 100*(tincometax+tearlytax)/tTaxable))
    print('total income (withdrawals + other) ${:,.0f}'.format(tincome))
    print('total cap gains tax: ${:0,.0f}'.format(tcg_tax))
    print('total all tax on all income: ${:0,.0f} ({:.1f}%)'.format(tincometax+tcg_tax+tearlytax, 100*(tincometax+tcg_tax+tearlytax)/tincome))
    print("Total spendable (after tax money): ${:0,.0f}".format(tspendable))
    if csvf is not None:
        csvf.write('\n')
        csvf.write("Optimized for %s\n" % S.maximize)
        csvf.write('\n')
        csvf.write('Minium desired: ${:0.0f}\n'.format(S.desired[0]))
        csvf.write('Maximum desired: ${:0.0f}\n'.format(S.max[0]))
        csvf.write('After tax yearly income: ${:0.0f} adjusting for inflation\n'.format(res.x[index_s(0)]))
        csvf.write('\n')
        csvf.write('total withdrawals: ${:0.0f}\n'.format(totwithd))
        csvf.write('total ordinary taxable income ${:.0f}\n'.format(tTaxable))
        csvf.write('total ordinary tax on all taxable income: ${:0.0f} ({:.1f}%) of taxable income\n'.format(tincometax+tearlytax, 100*(tincometax+tearlytax)/tTaxable))
        csvf.write('total income (withdrawals + orther) ${:.0f}\n'.format(tincome))
        csvf.write('total cap gains tax: ${:0.0f}\n'.format(tcg_tax))
        csvf.write('total all tax on all income: ${:0.0f} ({:.1f}%)\n'.format(tincometax+tcg_tax+tearlytax, 100*(tincometax+tcg_tax+tearlytax)/tincome))
        csvf.write("Total spendable (after tax money): ${:0.0f}\n".format(tspendable))

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
parser.add_argument('-mall', '--verbosemodelall', action='store_true',
                    help="Extra wga output from solver")
parser.add_argument('-csv', '--csv', action='store_true',
                    help="Additionally write the output from to a cvs file")
parser.add_argument('conffile')
args = parser.parse_args()

if args.csv:
    csv_file = open("a.csv", 'w')
else:
    csv_file = None

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
negitive_slack = S.numyr * (len(capgainstable)-1) # n[i,l]

nvars = tax_bracket_year + capital_gains_bracket_year + withdrawal_accounts_year + startbalance_accounts_year + spendable_year + investment_deposites_year + negitive_slack

res = solve()
consistancy_check(res)

print_model_results(res, csv_file)
if args.verbosetax:
    print_tax(res, csv_file)
if args.verbosetaxbrackets:
    print_tax_brackets(res, csv_file)
    print_cap_gains_brackets(res, csv_file)
print_base_config(res, csv_file)

if csv_file is not None:
    csv_file.close()