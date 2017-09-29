#!/usr/bin/python3

#
# A Retirement Planner (optimize withdrawals for most efficient use of the nest egg)
#

import toml
import argparse
import scipy.optimize
import re
import vector_var_index as vvar
import app_output as app_out

#from lp_constraint_model import build_model
import lp_constraint_model

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

    def maxContribution(self, year):
        ### not currently handling 401K max contributions TODO
        max = 0
        for v in self.retiree:
            max += contribspecs['IRARoth']
            age = v['ageAtStart'] +year
            if age >= contribspecs['CatchupAge']:
                max += contribspecs['IRARothCatchup']
        max *= S.i_rate ** year # adjust for inflation
        #print('maxContribution: ', max)
        return max

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
                r = self.match_retiree(k)
                if r is None:
                    if type == 'IRA' or type == 'roth':
                        print("Error: Account must match a retiree\n\t[%s.%s] should match [iam.%s] but there is no [iam.%s]\n"%(type,k,k,k))
                        exit(1)
                    ageAtStart = self.match_retiree(self.primary)['ageAtStart']
                else:
                    ageAtStart = r['ageAtStart']
                if 'contrib' not in v:
                    entry['contrib'] = 0
                    v['contrib'] = 0
                else:
                    entry['contrib'] = v['contrib']
                    if entry['contrib']>0:
                        if 'inflation' not in    v:
                            entry['inflation'] = False 
                        else:
                            entry['inflation'] = v['inflation']
                        period = v.get('period',None) 
                        if period is None:
                            print("%s account contribution needs a defined period of contribution." % type)
                            print("Please add the contribution period to the toml file in the [%s] section"%type)
                            exit(1)
                        entry['contributions'] = [0] * self.numyr
                        bucket = entry['contributions']
                        #print('period is: ', period)
                        for age in agelist(period):
                                year = age - ageAtStart #self.startage
                                if year < 0:
                                    continue
                                elif year >= self.numyr:
                                    break
                                else:
                                    bucket[year] = entry['contrib'] 
                                    if entry['inflation']:
                                        bucket[year] = entry['contrib'] * self.i_rate ** year
                                    #print("age %d, year %d, bucket: %6.0f += amount %6.0f" %(age, year, bucket[year], adj_amount))
                if type == 'aftertax':
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
                #print('entry: ', entry)
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
            secondarykey = ""
            if indx > 1:
                if lis_return[0]['primary'] == lis_return[1]['primary']:
                    print("Error: one of two retirees must be primary (i.e., primary = true):")
                    print("    [iam.%s] primary == %s" % (lis_return[0]['mykey'], lis_return[0]['primary']))
                    print("    [iam.%s] primary == %s" % (lis_return[1]['mykey'], lis_return[1]['primary']))
                    exit(1)
                if lis_return[1]['primary'] == True:
                    primaryIndx = 1
                    secondaryIndx = 0
                secondarykey = lis_return[secondaryIndx]['mykey']
                delta = lis_return[primaryIndx]['age'] - lis_return[secondaryIndx]['age']
                start = min(yearstoretire[0], yearstoretire[1]) + lis_return[primaryIndx]['age']
                lis_return[primaryIndx]['ageAtStart'] = start
                lis_return[secondaryIndx]['ageAtStart'] = start - delta
                end = max(yearsthrough[0], yearsthrough[1])+lis_return[primaryIndx]['age']
            #print("delta: %d, start: %d, end: %d, numyr: %d" %(delta, start, end, end-start))
            return lis_return, start, end-start, lis_return[primaryIndx]['mykey'], secondarykey, delta

        self.accounttable = []
        with open(file) as conffile:
            d = toml.loads(conffile.read())
        #print("\n\nun tarnished dict: ", d)
        #for f in d:
        #    print("\ndict[%s] = " % (f),d[f])
        #print()
        
        self.check_record( d, 'iam', ('age', 'retire', 'through', 'primary'))
        self.check_record( d, 'SocialSecurity', ('FRA', 'age', 'amount'))
        self.check_record( d, 'IRA', ('bal', 'rate', 'contrib', 'inflation', 'period'))
        self.check_record( d, 'roth', ('bal', 'rate', 'contrib', 'inflation', 'period'))
        self.check_record( d, 'aftertax', ('bal', 'rate', 'contrib', 'inflation', 'period', 'basis'))
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

        self.retiree, self.startage, self.numyr, self.primary, self.secondary, self.delta = get_retiree_info() # returns entry for each retiree
        #print("\nself.retiree: ", self.retiree, "\n\n")
        
        #print("input dictionary(processed): ", d)
        self.accounttable += get_account_info('IRA') # returns entry for each account
        self.accounttable += get_account_info('roth') 
        self.accounttable += get_account_info('aftertax') 
        #print("++Accounttable: ", self.accounttable)

        self.accmap = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(self.accounttable)):
            self.accmap[self.accounttable[j]['acctype']] += 1
        #print("Account Map ", self.accmap)

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
                        if tax is not None and v.get('tax'):
                            tax[year] += amount

        INC = [0] * self.numyr
        EXP = [0] * self.numyr
        TAX = [0] * self.numyr
        WANT = [0] * self.numyr
        MAX = [0] * self.numyr
        SS = [0] * self.numyr

        do_details("expense", EXP, None)
        do_details("income", INC, TAX)
        do_details("desired", WANT, None)
        do_details("max", MAX, None)
        do_SS_details(SS)

        self.income = INC
        self.expenses = EXP # WGA not currently in use
        self.taxed = TAX
        self.desired = WANT
        self.max = MAX
        self.SS = SS 

def precheck_consistancy():
    print("\nDoing Pre-check:")
    # check that there is income for all contibutions
        #tcontribs = 0
    for year in range(S.numyr):
        t = 0
        for j in range(len(S.accounttable)):
            if S.accounttable[j]['acctype'] != 'aftertax':
                v = S.accounttable[j]
                c = v.get('contributions', None)
                if c is not None: 
                    t += c[year]
        if t > S.income[year]:
            print("year: %d, contributions to Retirement accounts exceeds other earned income"%year)
            print("Please change the contributions in the toml file to be less than non-SS income.")
            exit(1)
    return True

def solve(c, A, b):

    res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                 options={"disp": args.verbose,
                                          #"bland": True,
                                          "tol": 1.0e-7,
                                          "maxiter": 3000})
    if args.verbosemodel or args.verbosemodelall:
        if res.success == False:
            print_model_matrix(c, A, b, None, False)
        else:
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
            if s is None or s[constraint] >0:
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

def consistancy_check(res, years, taxbins, cgbins, accounts, accmap, vindx):
    # check to see if the ordinary tax brackets are filled in properly
    print()
    print()
    print("Consistancy Checking:")
    print()

    result = vvar.my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, vindx)
    #result = my_check_index_sequence()
    print("IndexSequance result: ", result)

    for year in range(S.numyr):
        s = 0
        fz = False
        fnf = False
        i_mul = S.i_rate ** year
        for k in range(len(taxtable)): 
            cut, size, rate, base = taxtable[k]
            size *= i_mul
            s += res.x[vindx.x(year,k)] 
            if fnf and res.x[vindx.x(year,k)] > 0:
                print("Inproper packed brackets in year %d, bracket %d not empty while previous bracket not full." % (year, k))
            if res.x[vindx.x(year,k)]+1 < size:
                fnf = True
            if fz and res.x[vindx.x(year,k)] > 0:
                print("Inproperly packed tax brackets in year %d bracket %d" % (year, k))
            if res.x[vindx.x(year,k)] == 0.0:
                fz = True
        if S.accmap['aftertax'] > 0:
            scg = 0
            fz = False
            fnf = False
            for l in range(len(capgainstable)): 
                cut, size, rate = capgainstable[l]
                size *= i_mul
                bamount = res.x[vindx.y(year,l)] 
                scg += bamount
                for k in range(len(taxtable)-1):
                    if taxtable[k][0] >= capgainstable[l][0] and taxtable[k][0] < capgainstable[l+1][0]:
                        bamount += res.x[vindx.x(year,k)]
                if fnf and bamount > 0:
                    print("Inproper packed CG brackets in year %d, bracket %d not empty while previous bracket not full." % (year, l))
                if bamount+1 < size:
                    fnf = True
                if fz and bamount > 0:
                    print("Inproperly packed GC tax brackets in year %d bracket %d" % (year, l))
                if bamount == 0.0:
                    fz = True
        #TaxableOrdinary = res.x[vindx.w(year,0)] + S.income[year] -stded*i_mul
        TaxableOrdinary = OrdinaryTaxable(year)
        if (TaxableOrdinary + 0.1 < s) or (TaxableOrdinary - 0.1 > s):
            print("Error: Expected (age:%d) Taxable Ordinary income %6.2f doesn't match bracket sum %6.2f" % 
                (year + S.startage, TaxableOrdinary,s))

        for j in range(len(S.accounttable)):
            a = res.x[vindx.b(year+1,j)] -( res.x[vindx.b(year,j)] - res.x[vindx.w(year,j)] + res.x[vindx.D(year,j)])*S.accounttable[j]['rate']
            #a = res.x[vindx.b(year+1,j)] -( res.x[vindx.b(year,j)] - res.x[vindx.w(year,j)])*S.accounttable[j]['rate']
            if a > 1:
                v = S.accounttable[j]
                print("account[%d], type %s, index %d, mykey %s" % (j, v['acctype'], v['index'], v['mykey']))
                print("account[%d] year to year balance NOT OK years %d to %d" % (j, year, year+1))
                print("difference is", a)

        #last = len(S.accounttable)-1
        #D = 0
        #if S.accmap['aftertax'] > 0:
        #    D = res.x[vindx.D(year,last)]
        #if res.x[vindx.b(year+1,last)] -( res.x[vindx.b(year,last)] - res.x[vindx.w(year,last)] + D)*S.accounttable[last]['rate']>2:
        #    print("account[%d] year to year balance NOT OK years %d to %d" % (2, year, year+1))

        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        if spendable + 0.1 < res.x[vindx.s(year)]  or spendable -0.1 > res.x[vindx.s(year)]:
            print("Calc Spendable %6.2f should equal s(year:%d) %6.2f"% (spendable, year, res.x[vindx.s(year)]))
            for j in range(len(S.accounttable)):
                print("+w[%d,%d]: %6.0f" % (year, j, res.x[vindx.w(year,j)])) 
                #if S.accounttable[j]['acctype'] == 'aftertax':
                print("-D[%d,%d]: %6.0f" % (year, j, res.x[vindx.D(year,j)]))
            print("+o[%d]: %6.0f +SS[%d]: %6.0f -tax: %6.0f -cg_tax: %6.0f" % (year, S.income[year] ,year, S.SS[year] , tax ,cg_tax))

        bt = 0
        for k in range(len(taxtable)):
            bt += res.x[vindx.x(year,k)] * taxtable[k][2]
        if tax + 0.1 < bt  or tax -0.1 > bt:
            print("Calc tax %6.2f should equal brackettax(bt)[]: %6.2f" % (tax, bt))
        #if cg_tax + 0.1 < res.x[vindx.Fcg(year)]  or cg_tax -0.1 > res.x[vindx.Fcg(year)]:
        #    print("Calc cg_tax %6.2f should equal Fcg(year:%d): %6.2f" % (cg_tax, year, res.x[vindx.Fcg(year)]))
    print()

"""
def ao.output(string): # TODO move to a better place
    #
    # output writes the information after first changing any '@' in the string
    # to a space for stdout or a ',' for csv files. The later is written
    # whenever the csv_file handle is not None
    #
    sys.stdout.write(string.replace('@',' '))
    if csv_file is not None:
        csv_file.write(string.replace('@',','))
"""

def print_model_results(res): 
    def printheader1():
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")

        ao.output(("@%7s" * 12) % ("fIRA", "tIRA", "RMDref", "fRoth", "tRoth", "fAftaTx", "tAftaTx", "o_inc", "SS", "Expense", "TFedTax", "Spndble"))
        ao.output("\n")

    ao.output("\nActivity Summary:\n")
    ao.output('\n')
    printheader1()
    for year in range(S.numyr):
        i_mul = S.i_rate ** year
        age = year + S.startage
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)

        rmdref = 0
        for j in range(min(2,len(S.accounttable))): # at most the first two accounts are type IRA w/ RMD requirement
            if S.accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,S.accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref += res.x[vindx.b(year,j)]/rmd 

        #balance = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        deposit = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(S.accounttable)):
            #balance[S.accounttable[j]['acctype']] += res.x[vindx.b(year,j)]
            withdrawal[S.accounttable[j]['acctype']] += res.x[vindx.w(year,j)]
            deposit[S.accounttable[j]['acctype']] += res.x[vindx.D(year,j)]
        #D = 0
        #if S.accmap['aftertax'] > 0:
        #    D = res.x[vindx.D(year, len(S.accounttable)-1)]/1000.0

        if S.secondary != "":
            ao.output("%3d/%3d:" % (year+S.startage, year+S.startage-S.delta))
        else:
            ao.output(" %3d:" % (year+S.startage))
        ao.output(("@%7.0f" * 11 ) %
              ( withdrawal['IRA']/1000.0, deposit['IRA']/1000.0, rmdref/1000.0, # IRA
                withdrawal['roth']/1000.0, deposit['roth']/1000.0,  # Roth
                withdrawal['aftertax']/1000.0, deposit['aftertax']/1000.0,  #D, # AftaTax
                S.income[year]/1000.0, S.SS[year]/1000.0, S.expenses[year]/1000.0,
                (tax+cg_tax+earlytax)/1000.0) )
        #ao.output(("@%7.0f" * 12 ) %
        #      ( balance['IRA']/1000.0, withdrawal['IRA']/1000.0, rmdref/1000.0, # IRA
        #        balance['roth']/1000.0, withdrawal['roth']/1000.0, # Roth
        #        balance['aftertax']/1000.0, withdrawal['aftertax']/1000.0, D, # AftaTax
        #        S.income[year]/1000.0, S.SS[year]/1000.0, S.expenses[year]/1000.0,
        #        (tax+cg_tax+earlytax)/1000.0) )
        s = res.x[vindx.s(year)]/1000.0
        star = ' '
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        if spendable + 0.1 < res.x[vindx.s(year)]  or spendable -0.1 > res.x[vindx.s(year)]:
            s = spendable/1000.0
            star = '*'
        ao.output("@%7.0f%c" % (s, star) )
        ao.output("\n")

    #year = S.numyr
    #balance = {'IRA': 0, 'roth': 0, 'aftertax': 0}
    #for j in range(len(S.accounttable)):
    #    balance[S.accounttable[j]['acctype']] += res.x[vindx.b(year,j)]
    #if S.secondary != "":
    #    ao.output("  final:" )
    #else:
    #    ao.output("finl:" )
    #ao.output(("@%7.0f@%7s@%7s" + "@%7.0f@%7s" * 2 + "@%7s" * 6) %
    #    ( 
    #    balance['IRA']/1000.0, '-', '-',  # res.x[vindx.w(year,0)]/1000.0, # IRA
    #    balance['roth']/1000.0, '-', # res.x[vindx.w(year,1)]/1000.0, # Roth
    #    balance['aftertax']/1000.0, '-', # res.x[vindx.w(year,2)]/1000.0, # AftaTax
    #    '-', '-', '-', '-', '-', '-'))
    #ao.output("\n")
    printheader1()

def print_account_trans(res):
    def print_acc_header1():
        #ao.output("%s\n" % S.who)
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        if S.accmap['IRA'] >1:
            ao.output(("@%7s" * 8) % ("IRA1", "fIRA1", "tIRA1", "RMDref1", "IRA2", "fIRA2", "tIRA2", "RMDref2"))
        elif S.accmap['IRA'] == 1:
            ao.output(("@%7s" * 4) % ("IRA", "fIRA", "tIRA", "RMDref"))
        if S.accmap['roth'] >1:
            ao.output(("@%7s" * 6) % ("Roth1", "fRoth1", "tRoth1", "Roth2", "fRoth2", "tRoth2"))
        elif S.accmap['roth'] == 1:
            ao.output(("@%7s" * 3) % ("Roth", "fRoth", "tRoth"))
        if S.accmap['IRA']+S.accmap['roth'] == len(S.accounttable)-1:
            ao.output(("@%7s" * 3) % ("AftaTx", "fAftaTx", "tAftaTx"))
        ao.output("\n")

    ao.output("\nAccount Transactions Summary:\n\n")
    print_acc_header1()
    for year in range(S.numyr):
        #age = year + S.startage #### who's age??? NEED BOTH!!!!
        rmdref = [0,0]
        for j in range(min(2,len(S.accounttable))): # only first two accounts are type IRA w/ RMD
            if S.accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,S.accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref[j] = res.x[vindx.b(year,j)]/rmd 

        if S.secondary != "":
            ao.output("%3d/%3d:" % (year+S.startage, year+S.startage-S.delta))
        else:
            ao.output(" %3d:" % (year+S.startage))
        if S.accmap['IRA'] >1:
            ao.output(("@%7.0f" * 8) % (
              res.x[vindx.b(year,0)]/1000.0, res.x[vindx.w(year,0)]/1000.0, res.x[vindx.D(year,0)]/1000.0, rmdref[0]/1000.0, # IRA1
              res.x[vindx.b(year,1)]/1000.0, res.x[vindx.w(year,1)]/1000.0, res.x[vindx.D(year,1)]/1000.0, rmdref[1]/1000.0)) # IRA2
        elif S.accmap['IRA'] == 1:
            ao.output(("@%7.0f" * 4) % (
              res.x[vindx.b(year,0)]/1000.0, res.x[vindx.w(year,0)]/1000.0, res.x[vindx.D(year,0)]/1000.0, rmdref[0]/1000.0)) # IRA1
        index = S.accmap['IRA']
        if S.accmap['roth'] >1:
            ao.output(("@%7.0f" * 6) % (
              res.x[vindx.b(year,index)]/1000.0, res.x[vindx.w(year,index)]/1000.0, res.x[vindx.D(year,index)]/1000.0, # roth1
              res.x[vindx.b(year,index+1)]/1000.0, res.x[vindx.w(year,index+1)]/1000.0, res.x[vindx.D(year,index+1)]/1000.0)) # roth2
        elif S.accmap['roth'] == 1:
            ao.output(("@%7.0f" * 3) % (
              res.x[vindx.b(year,index)]/1000.0, res.x[vindx.w(year,index)]/1000.0, res.x[vindx.D(year,index)]/1000.0)) # roth1
        index = S.accmap['IRA'] + S.accmap['roth']
        #assert index == len(S.accounttable)-1
        if index == len(S.accounttable)-1:
            ao.output(("@%7.0f" * 3) % (
                res.x[vindx.b(year,index)]/1000.0, 
                res.x[vindx.w(year,index)]/1000.0, 
                res.x[vindx.D(year,index)]/1000.0)) # aftertax account
        ao.output("\n")
    print_acc_header1()

def print_tax(res):
    def printheader_tax():
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        ao.output(("@%7s" * 13) %
          ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "earlyP", "fedtax", "mTaxB%", "fAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble" ))
        ao.output("\n")

    ao.output("\nTax Summary:\n\n")
    printheader_tax()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        f = lp_constraint_model.cg_taxable_fraction(S, year)
        ttax = tax + cg_tax +earlytax
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(S.accounttable)):
            withdrawal[S.accounttable[j]['acctype']] += res.x[vindx.w(year,j)]
        if S.secondary != "":
            ao.output("%3d/%3d:" % (year+S.startage, year+S.startage-S.delta))
        else:
            ao.output(" %3d:" % (year+S.startage))
        ao.output(("@%7.0f" * 13 ) %
              ( withdrawal['IRA']/1000.0, # sum IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, earlytax/1000.0, tax/1000.0, rate*100, 
                withdrawal['aftertax']/1000.0, # sum Aftertax
              f*100, cg_tax/1000.0,
              ttax/1000.0, res.x[vindx.s(year)]/1000.0 ))
        ao.output("\n")
    printheader_tax()

def print_tax_brackets(res):
    def printheader_tax_brackets():
        if S.secondary != "":
            ao.output("@@@@@@%50s" % "Marginal Rate(%):")
        else:
            ao.output("@@@@@@%47s" % "Marginal Rate(%):")
        for k in range(len(taxtable)):
            (cut, size, rate, base) = taxtable[k]
            ao.output("@%6.0f" % (rate*100))
        ao.output("\n")
        #ao.output("%s\n"%S.who)
        #ao.output("%s/%s\n" % (S.primary, S.secondary))
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        ao.output(("@%7s" * 6) % ("fIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "fedtax"))
        for k in range(len(taxtable)):
            ao.output("@brckt%d" % k)
        ao.output("@brkTot\n")

    ao.output("\nOverall Tax Bracket Summary:\n")
    printheader_tax_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        if S.secondary != "":
            ao.output("%3d/%3d:" % (year+S.startage, year+S.startage-S.delta))
        else:
            ao.output(" %3d:" % (year+S.startage))
        ao.output(("@%7.0f" * 6 ) %
              (
              res.x[vindx.w(year,0)]/1000.0, # IRA
              S.taxed[year]/1000.0, SS_taxable*S.SS[year]/1000.0,
              stded*i_mul/1000.0, T/1000.0, tax/1000.0) )
        bt = 0
        for k in range(len(taxtable)):
            ao.output("@%6.0f" % res.x[vindx.x(year,k)])
            bt += res.x[vindx.x(year,k)]
        ao.output("@%6.0f\n" % bt)
    printheader_tax_brackets()

def print_cap_gains_brackets(res):
    def printheader_capgains_brackets():
        if S.secondary != "":
            ao.output("@@@@@@%42s" % "Marginal Rate(%):")
        else:
            ao.output("@@@@@%40s" % " Marginal Rate(%):")
        for l in range(len(capgainstable)):
            (cut, size, rate) = capgainstable[l]
            ao.output("@%6.0f" % (rate*100))
        ao.output("\n")
        #ao.output("%s\n"%S.who)
        #ao.output("%s/%s\n" % (S.primary, S.secondary))
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        ao.output(("@%7s" * 5) % ("fAftaTx","cgTax%", "cgTaxbl", "T_inc", "cgTax"))
        for l in range(len(capgainstable)):
            ao.output("@brckt%d" % l)
        ao.output("@brkTot\n")

    ao.output("\nOverall Capital Gains Bracket Summary:\n")
    printheader_capgains_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** year
        f = 1
        atw = 0
        att = 0
        if S.accmap['aftertax'] > 0:
            f = lp_constraint_model.cg_taxable_fraction(S, year)
            j = len(S.accounttable)-1 # Aftertax / investment account always the last entry when present
            atw = res.x[vindx.w(year,j)]/1000.0 # Aftertax / investment account
            att = (f*res.x[vindx.w(year,j)])/1000.0 # non-basis fraction / cg taxable $ 
        T,spendable,tax,rate,cg_tax,earlytax = IncomeSummary(year)
        ttax = tax + cg_tax
        if S.secondary != "":
            ao.output("%3d/%3d:" % (year+S.startage, year+S.startage-S.delta))
        else:
            ao.output(" %3d:" % (year+S.startage))
        ao.output(("@%7.0f" * 5 ) %
              (
              atw, # Aftertax / investment account
              f*100, att, # non-basis fraction / cg taxable $ 
              T/1000.0, cg_tax/1000.0))
        bt = 0
        bttax = 0
        for l in range(len(capgainstable)):
            ty = 0
            if S.accmap['aftertax'] > 0:
                ty = res.x[vindx.y(year,l)]
            ao.output("@%6.0f" % ty)
            bt += ty
            bttax += ty * capgainstable[l][2]
        ao.output("@%6.0f\n" % bt)
        if args.verbosewga:
            print(" cg bracket ttax %6.0f " % bttax, end='')
            print("x->y[1]: %6.0f "% (res.x[vindx.x(year,0)]+res.x[vindx.x(year,1)]),end='')
            print("x->y[2]: %6.0f "% (res.x[vindx.x(year,2)]+ res.x[vindx.x(year,3)]+ res.x[vindx.x(year,4)]+res.x[vindx.x(year,5)]),end='')
            print("x->y[3]: %6.0f"% res.x[vindx.x(year,6)])
        # TODO move to consistancy_check()
        #if (capgainstable[0][1]*i_mul -(res.x[vindx.x(year,0)]+res.x[vindx.x(year,1)])) <= res.x[vindx.y(year,1)]:
        #    print("y[1]remain: %6.0f "% (capgainstable[0][1]*i_mul -(res.x[vindx.x(year,0)]+res.x[vindx.x(year,1)])))
        #if (capgainstable[1][1]*i_mul - (res.x[vindx.x(year,2)]+ res.x[vindx.x(year,3)]+ res.x[vindx.x(year,4)]+res.x[vindx.x(year,5)])) <= res.x[vindx.y(year,2)]:
        #    print("y[2]remain: %6.0f " % (capgainstable[1][1]*i_mul - (res.x[vindx.x(year,2)]+ res.x[vindx.x(year,3)]+ res.x[vindx.x(year,4)]+res.x[vindx.x(year,5)])))
    printheader_capgains_brackets()

def print_constraint(row, b):
    print_model_row(row, True)
    print("<= b[]: %6.2f" % b)

def print_model_row(row, suppress_newline = False):
    for i in range(S.numyr):
        for k in range(len(taxtable)):
            if row[vindx.x(i, k)] != 0:
                print("x[%d,%d]: %6.3f" % (i, k, row[vindx.x(i, k)]),end=' ' )
    if S.accmap['aftertax'] > 0:
        for i in range(S.numyr):
            for l in range(len(capgainstable)):
                if row[vindx.y(i, l)] != 0:
                    print("y[%d,%d]: %6.3f " % (i, l, row[vindx.y(i, l)]),end=' ' )
    for i in range(S.numyr):
        for j in range(len(S.accounttable)):
            if row[vindx.w(i, j)] != 0:
                print("w[%d,%d]: %6.3f " % (i, j, row[vindx.w(i, j)]),end=' ' )
    for i in range(S.numyr+1): # b[] has an extra year
        for j in range(len(S.accounttable)):
            if row[vindx.b(i, j)] != 0:
                print("b[%d,%d]: %6.3f " % (i, j, row[vindx.b(i, j)]),end=' ' )
    for i in range(S.numyr):
        if row[vindx.s(i)] !=0:
            print("s[%d]: %6.3f " % (i, row[vindx.s(i)]),end=' ' )
    if S.accmap['aftertax'] > 0:
        for i in range(S.numyr):
            for j in range(len(S.accounttable)):
                if row[vindx.D(i,j)] !=0:
                    print("D[%d,%d]: %6.3f " % (i, j, row[vindx.D(i,j)]),end=' ' )
    if not suppress_newline:
        print()

"""
def cg_taxable_fraction(year):
    f = 1
    if S.accmap['aftertax'] > 0:
        for v in S.accounttable:
            if v['acctype'] == 'aftertax':
                f = 1 - (v['basis']/(v['bal']*v['rate']**year))
                break # should be the last entry anyway but...
    #f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
    return f
"""

def OrdinaryTaxable(year):
    withdrawals = 0 
    for j in range(min(2,len(S.accounttable))):
        if S.accounttable[j]['acctype'] == 'IRA':
            withdrawals += res.x[vindx.w(year,j)]
    T = withdrawals + S.taxed[year] + SS_taxable*S.SS[year] -(stded*S.i_rate**year)
    if T < 0:
        T = 0
    return T

def IncomeSummary(year):
    # TODO clean up and simplify this fuction
    #
    # return OrdinaryTaxable, Spendable, Tax, Rate, CG_Tax
    # Need to account for withdrawals from IRA deposited in Investment account NOT SPENDABLE
    age = year + S.startage
    earlytax = 0
    for j in range(len(S.accounttable)):
        if S.accounttable[j]['acctype'] != 'aftertax':
            if S.apply_early_penalty(year,S.accounttable[j]['mykey']):
                earlytax += res.x[vindx.w(year,j)]*penalty
    T = OrdinaryTaxable(year)
    ntax = 0
    rate = 0
    for k in range(len(taxtable)):
        ntax += res.x[vindx.x(year,k)]*taxtable[k][2]
        if res.x[vindx.x(year,k)] > 0:
            rate = taxtable[k][2]
    tax = ntax
    D = 0
    ncg_tax = 0
    #if S.accmap['aftertax'] > 0:
    for j in range(len(S.accounttable)):
        D +=  res.x[vindx.D(year,j)]
    if S.accmap['aftertax'] > 0:
        for l in range(len(capgainstable)):
            ncg_tax += res.x[vindx.y(year,l)]*capgainstable[l][2]
    tot_withdrawals = 0
    for j in range(len(S.accounttable)):
        tot_withdrawals += res.x[vindx.w(year,j)] 
    spendable = tot_withdrawals - D + S.income[year] + S.SS[year] - S.expenses[year] - tax -ncg_tax - earlytax
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
        for j in range(len(S.accounttable)):
            tot_withdrawals += res.x[vindx.w(year,j)] 
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
    ao.output("\n")
    ao.output("Optimized for %s\n" % S.maximize)
    ao.output('Minium desired: ${:0_.0f}\n'.format(S.desired[0]))
    ao.output('Maximum desired: ${:0_.0f}\n'.format(S.max[0]))
    ao.output('After tax yearly income: ${:0_.0f} adjusting for inflation\n'.format(res.x[vindx.s(0)]))
    ao.output("\n")
    ao.output('total withdrawals: ${:0_.0f}\n'.format(totwithd))
    ao.output('total ordinary taxable income ${:_.0f}\n'.format(tTaxable))
    ao.output('total ordinary tax on all taxable income: ${:0_.0f} ({:.1f}%) of taxable income\n'.format(tincometax+tearlytax, 100*(tincometax+tearlytax)/tTaxable))
    ao.output('total income (withdrawals + other) ${:_.0f}\n'.format(tincome))
    ao.output('total cap gains tax: ${:0_.0f}\n'.format(tcg_tax))
    ao.output('total all tax on all income: ${:0_.0f} ({:.1f}%)\n'.format(tincometax+tcg_tax+tearlytax, 100*(tincometax+tcg_tax+tearlytax)/tincome))
    ao.output("Total spendable (after tax money): ${:0_.0f}\n".format(tspendable))

# Program entry point
# Instantiate the parser
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--verbose', action='store_true',
                    help="Extra output from solver")
parser.add_argument('-va', '--verboseaccounttrans', action='store_true',
                    help="Output detailed account transactions from solver")
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

csv_file_name = None
if args.csv:
    csv_file_name = 'a.csv'
ao = app_out.app_output(csv_file_name)

S = Data()
S.load_file(args.conffile)

#print("\naccounttable: ", S.accounttable)

if S.accmap['IRA']+S.accmap['roth']+S.accmap['aftertax'] == 0:
    print('Error: This app optimizes the withdrawals from your retirement account(s); you must have at least one specified in the input toml file.')
    exit(0)

if args.verbosewga:
    print("accounttable: ", S.accounttable)

non_binding_only = True
if args.verbosemodelall:
    non_binding_only = False

years = S.numyr
taxbins = len(taxtable) 
cgbins = len(capgainstable) 
accounts = len(S.accounttable) 
        
vindx = vvar.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
nvars = vindx.vsize

if precheck_consistancy():
    c, A, b = lp_constraint_model.build_model(S, vindx, taxtable, capgainstable, penalty, stded, SS_taxable, args)
    res = solve(c, A, b)
    consistancy_check(res, years, taxbins, cgbins, accounts, S.accmap, vindx)

    print_model_results(res)
    if args.verboseaccounttrans:
        print_account_trans(res)
    if args.verbosetax:
        print_tax(res)
    if args.verbosetaxbrackets:
        print_tax_brackets(res)
        print_cap_gains_brackets(res)
    print_base_config(res)
