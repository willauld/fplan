#!/usr/bin/python3

import toml
import argparse
import scipy.optimize
import re

# 2017 table (could predict it moves with inflation?)
# only married joint at the moment
# [braket $ start, bracket size, marginal rate, total tax from all lower brackets]
taxtable = [[0,      0.1,     0.00, 0],
            [0.1,    18699.9, 0.10, 0.01],        # fake level to fix 0
            [18700,  57200,   0.15, 1900],
            [75900,  77200,   0.25, 10500],
            [153100, 80300,   0.28, 29800],
            [233400, 182300,  0.33, 52200],
            [415700, 54300,   0.35, 112400],
            [470000, -1,      0.40, 131400]]
stded = 12700 + 2*4050    # standard deduction + 2 personal exemptions for joint filing

accounttable = [] # array of [bal, rate]

# Required Minimal Distributions from IRA starting with age 70
RMD = [27.4, 26.5, 25.6, 24.7, 23.8, 22.9, 22.0, 21.2, 20.3, 19.5,  # age 70-79
       18.7, 17.9, 17.1, 16.3, 15.5, 14.8, 14.1, 13.4, 12.7, 12.0,  # age 80-89
       11.4, 10.8, 10.2,  9.6,  9.1,  8.6,  8.1,  7.6,  7.1,  6.7,  # age 90-99
        6.3,  5.9,  5.5,  5.2,  4.9,  4.5,  4.2,  3.9,  3.7,  3.4,  # age 100+
        3.1,  2.9,  2.6,  2.4,  2.1,  1.9,  1.9,  1.9,  1.9,  1.9]

cg_tax = 0.15                   # capital gains tax rate

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
        self.i_rate = 1 + d.get('inflation', 0) / 100       # inflation rate: 2.5 -> 1.025
        self.r_rate = 1 + d.get('returns', 6) / 100         # invest rate: 6 -> 1.06

        self.startage = d['startage']
        self.endage = d.get('endage', max(96, self.startage+5))
        if 'prep' in d:
            self.workyr = d['prep']['workyears']
            self.maxsave = d['prep']['maxsave']
            # I believe the calculation here should be worktax = 1/(1-tax_rate) WGA
            self.worktax = 1 + d['prep'].get('tax_rate', 25)/100
        else:
            self.workyr = 0
        self.retireage = self.startage + self.workyr
        self.numyr = self.endage - self.retireage

        self.aftertax = d.get('aftertax', {'bal': 0})
        if 'basis' not in self.aftertax:
            self.aftertax['basis'] = 0

        self.IRA1 = d.get('IRA1', {'bal':0})
        if 'rate' not in self.IRA1:
            self.IRA1['rate'] = self.r_rate 
        else:
            self.IRA1['rate'] = 1 + self.IRA1['rate'] / 100         # invest rate: 6 -> 1.06
        self.accounttable+=[[self.IRA1['bal'], self.IRA1['rate']]]
        self.IRA2 = d.get('IRA2', {'bal':0})
        if 'rate' not in self.IRA2:
            self.IRA2['rate'] = self.r_rate 
        else:
            self.IRA2['rate'] = 1 + self.IRA2['rate'] / 100         # invest rate: 6 -> 1.06
        self.accounttable+=[[self.IRA2['bal'], self.IRA2['rate']]]

        self.IRA = d.get('IRA', {'bal': 0})
        if 'maxcontrib' not in self.IRA:
            self.IRA['maxcontrib'] = 18000 + 5500*2

        self.roth = d.get('roth', {'bal': 0});
        if 'maxcontrib' not in self.roth:
            self.roth['maxcontrib'] = 5500*2

        self.parse_expenses(d)
        self.sepp_end = max(5, 59-self.retireage)     # first year you can spend IRA reserved for SEPP
        self.sepp_ratio = 25                         # money per-year from SEPP  (bal/ratio)

    def parse_expenses(self, S):
        """ Return array of income/expense per year """
        INC = [0] * self.numyr
        EXP = [0] * self.numyr
        TAX = [0] * self.numyr
        WANT = [0] * self.numyr

        for k,v in S.get('expense', {}).items():
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
                    EXP[year] += amount

        for k,v in S.get('income', {}).items():
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
                    INC[year] += amount
                    if v.get('tax'):
                        TAX[year] += amount

        for k,v in S.get('desired', {}).items():
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
                    WANT[year] += amount
                    #if v.get('tax'):
                    #    TAX[year] += amount

        self.income = INC
        self.expenses = EXP
        self.taxed = TAX
        self.desired = WANT

# Minimize: c^T * x
# Subject to: A_ub * x <= b_ub
#vars: money, per year(savings, ira, roth, ira2roth)  (193 vars)
#all vars positive
def solve():
    nvars = tax_bracket_year + withdrawal_accounts_year + startbalance_accounts_year

    #
    # Define the object function (1')
    #
    c = [0] * nvars
    for year in range(S.numyr):
        pv = S.i_rate**(-year) # using inflation rate as the risk free discount rate for pv
        k = 0
        for (cut, size, rate, base) in taxtable:
            if args.verbosewga:
                print("year: ", year, "k: ", k,  "pv: ", pv, "rate: ", rate, "pv*(rate-1): ", pv*(rate-1))
            c[index_x(year,k)] = pv*(rate-1) # -pv*(1-rate) == pv*(rate-1)
            k+=1

    pv_n = S.i_rate**(-S.numyr)
    for j in range(len(accounttable)):
        if args.verbosewga:
            print("index: ", index_b(S.numyr,j), "acc: ", j, "-1*pv_n: ", -1*pv_n)
        c[index_b(S.numyr,j)] = -1*pv_n

    A = []
    b = []

    #
    # Add constrant (2') rows
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(accounttable)):
            row[index_w(year,j)] = -1
        A+=[row]
        b+=[ S.income[year] - S.desired[year] ]     # [o_i - d_i]

    #
    # Add constaints for (3') rows
    #
    for year in range(S.numyr):
        age = year + S.retireage
        if age >= 70:
            row = [0] * nvars
            rmd = RMD[age - 70]
            for j in range(len(accounttable)):
                row[index_b(year,j)] = 1/rmd
                row[index_w(year,j)] = -1
            A+=[row]
            b+=[0]

    #
    # Add constraints for (4a')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for k in range(len(taxtable)):
            row[index_x(year,k)] = 1
        for j in range(len(accounttable)):
            row[index_w(year,j)] = -1
        A+=[row]
        b+=[S.income[year]-stded*adj_inf]
    #
    # Add constraints for (4b')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for j in range(len(accounttable)):
            row[index_w(year,j)] = 1
        for k in range(len(taxtable)):
            row[index_x(year,k)] = -1
        A+=[row]
        b+=[stded*adj_inf-S.income[year]]
    #
    # Add constraints for (5')
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)-1):
            row = [0] * nvars
            row[index_x(year,k)] = 1
            A+=[row]
            b+=[(taxtable[k][1])*(S.i_rate**year)] # inflation adjusted
    #
    # Add constraints for (6a')
    #
    for year in range(S.numyr):
        for j in range(len(accounttable)):
            row = [0] * nvars
            row[index_b(year+1,j)] = 1
            row[index_b(year,j)] = -1*accounttable[j][1]
            row[index_w(year,j)] = accounttable[j][1]
            A+=[row]
            b+=[0]
    #
    # Add constraints for (6b')
    #
    for year in range(S.numyr):
        for j in range(len(accounttable)):
            row = [0] * nvars
            row[index_b(year,j)] = accounttable[j][1]
            row[index_w(year,j)] = -1*accounttable[j][1]
            row[index_b(year+1,j)] = -1
            A+=[row]
            b+=[0]
    #
    # Constraint for (7a') (New not in Ragsdale paper)
    #   Set the begining b[1,j] balances
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = 1
        A+=[row]
        b+=[accounttable[j][0]]

    #
    # Constraint for (7b') (New not in Ragsdale paper)
    #   Set the begining b[1,j] balances
    for j in range(len(accounttable)):
        row = [0] * nvars
        row[index_b(0,j)] = -1
        A+=[row]
        b+=[-1*accounttable[j][0]]

    #
    # Constrant for (8') is default for sycpy so no code is needed
    #

    if args.verbose:
        print("Num vars: ", len(c))
        print("Num contraints: ", len(b))
        print()
    if args.verbosewga:
        print("c: ", c)
        print()
        print("i: A_ub[i]: b[i]")
        for constraint in range(len(A)):
            print(constraint, ":", A[constraint], b[constraint])
        print()

    res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                 options={"disp": args.verbose,
                                          #"bland": True,
                                          "tol": 1.0e-7,
                                          "maxiter": 3000})
    if res.success == False:
        print(res)
        exit(1)

    if args.verbosewga:
        print(res)

    return res #res.x

def process_and_print_ascii(res):
    def printheader():
        print((" age" + " %7s" * 10) %
          ("IRA1", "fIRA1", "IRA2", "fIRA2", "o_inc", "T_inc", "fedtax", "mTaxB%", "RMDref", "Desired"))

    twithd = 0 
    ttax = 0
    tT = 0
    pv_twithd = 0; pv_ttax = 0; pv_tT = 0
    printheader()
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        discountR = S.i_rate**-year # use rate of inflation as discount rate
        age = year + S.retireage
        if age >= 70:
            rmd = RMD[age - 70]
        T = res.x[index_w(year,0)] + res.x[index_w(year,1)] + S.income[year]
        sum = 0
        for k in range(len(taxtable)):
            (cut, size, rate, base) = taxtable[k]
            cut *= i_mul
            size *= i_mul
            base *= i_mul
            if args.verbosewga:
                sum += res.x[index_x(year,k)]
                print(("inf adj taxtable[k]: [" + " %5.2f" *4 + "], x[%d,%d]: %5.2f, sum: %5.0f") % 
                    (cut, size, rate, base, year, k, res.x[index_x(year,k)], sum))
            if size - res.x[index_x(year,k)] > 10:
                if args.verbosewga:
                    if T-cut > res.x[index_x(year,k)]  or T-cut < res.x[index_x(year,k)] :
                        print(("T{%5.0f} - cut{%5.0f} = %5.0f should equal x[%d,%d]{%5.0f}")% 
                            (T, cut, T-cut, year, k, res.x[index_x(year,k)] ))
                        print(("w[%d,%d]{%5.0f}+w[%d,%d]{%5.0f}+o[%d]{%5.0f}")%
                            (year, 0, res.x[index_w(year,0)], year, 1, res.x[index_w(year,1)],year, S.income[year]))
                        #print("T - cut", T-cut, "should equal x(i,k):", res.x[index_x(year,k)] )
                        print("NEXT LINE DELTA SHOULD BE SMALL:")
                        print(("(T - cut) - x(i,k): %5.4f") % ((T -cut)- res.x[index_x(year,k)] ))
                    if res.x[index_x(year,k+1)] > 0:
                        print("missing applicable tax braket ", k+1, "th")

                break
        tax = (T - cut) * rate + base
        if age >= 70:
            rmdref = (res.x[index_b(year,0)] + res.x[index_b(year,1)])/rmd 
        else:
            rmdref = 0
        if args.verbosecheck:
            if res.x[index_b(year+1,0)] -( res.x[index_b(year,0)] - res.x[index_w(year,0)])*accounttable[0][1]<10:
                print("account[0] year to year balance OK")
            else:
                print("account[0] year to year balance NOT OK")
            if res.x[index_b(year+1,1)] -( res.x[index_b(year,1)] - res.x[index_w(year,1)])*accounttable[1][1]<10:
                print("account[1] year to year balance OK")
            else:
                print("account[1] year to year balance NOT OK")

        print((" %d:" + " %7.0f" * 10 ) %
              (year+S.retireage, 
              res.x[index_b(year,0)]/1000.0, res.x[index_w(year,0)]/1000.0, 
              res.x[index_b(year,1)]/1000.0, res.x[index_w(year,1)]/1000.0, 
              S.income[year]/1000.0, T/1000.0, tax/1000.0, rate*100, rmdref/1000.0, 
              S.desired[year]/1000.0))
        twithd += res.x[index_w(year,0)] + res.x[index_w(year,1)] 
        ttax += tax
        tT += T
        pv_twithd += (res.x[index_w(year,0)] + res.x[index_w(year,1)] )* discountR
        pv_ttax += tax *discountR
        pv_tT += T*discountR

    printheader()
    print("\ntotal withdrawals: %.0f, total income %.0f" % (twithd, tT))
    print("total tax on all income: %.0f (%.1f%%)" % (ttax, 100*ttax/tT))

    print("\ntotal pv withdrawals: %.0f, total pv income %.0f" % (pv_twithd, pv_tT))
    print("total pv tax on all income: %.0f (%.1f%%)" % (pv_ttax, 100*ttax/tT))

def print_csv(res):
    print("spend goal,%d" % res[0])
    print("savings,%d,%d" % (S.aftertax['bal'], S.aftertax['basis']))
    print("ira,%d" % S.IRA['bal'])
    print("roth,%d" % S.roth['bal'])

    print("age,spend,fIRA,fROTH,IRA2R,income,expense");
    for year in range(S.numyr):
        fsavings = res[n0+year*vper]
        fira = res[n0+year*vper+1]
        froth = res[n0+year*vper+2]
        ira2roth = res[n0+year*vper+3]
        print(("%d," * 6 + "%d") % (year+S.retireage,fsavings,fira,froth,ira2roth,
                                    S.income[year],S.expenses[year]))

def index_x(i, k):
    return i*len(taxtable)+k
def index_w(i,j):
    return tax_bracket_year+i*len(accounttable)+j
def index_b(i,j):
    return tax_bracket_year+withdrawal_accounts_year+i*len(accounttable)+j

# Instantiate the parser
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true',
                    help="Extra output from solver")
parser.add_argument('-vw', '--verbosewga', action='store_true',
                    help="Extra wga output from solver")
parser.add_argument('-vc', '--verbosecheck', action='store_true',
                    help="Extra checking of output from solver")
parser.add_argument('--sepp', action='store_true',
                    help="Enable SEPP processing")
parser.add_argument('--noIRA2R', action='store_true',
                    help="Disable IRA2Roth processing")
parser.add_argument('--csv', action='store_true', help="Generate CSV outputs")
parser.add_argument('conffile')
args = parser.parse_args()

S = Data()
S.load_file(args.conffile)
accounttable = S.accounttable
if args.verbosewga:
    print("accounttable: ", accounttable)
tax_bracket_year = S.numyr * len(taxtable) # x[i,k]
withdrawal_accounts_year = S.numyr * len(accounttable) # w[i,j]
startbalance_accounts_year = (S.numyr+1) * len(accounttable) # b[i,j]

res = solve()
if args.csv:
    print_csv(res)
else:
    process_and_print_ascii(res)
