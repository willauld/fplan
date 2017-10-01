#!/usr/bin/python3

#
# A Retirement Planner (optimize withdrawals for most efficient use of the nest egg)
#

#import toml
import argparse
import scipy.optimize
import re
#import taxinfo ### TODO replace the following line with this one and edits to this file
from taxinfo import accountspecs, taxtable, capgainstable, penalty, stded, SS_taxable, contribspecs, RMD
import tomldata
import vector_var_index as vvar
import app_output as app_out
import lp_constraint_model as lp

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
            model.print_model_matrix(c, A, b, None, False)
        else:
            model.print_model_matrix(c, A, b, res.slack, non_binding_only)
    if args.verbosewga:
        print(res)

    if res.success == False:
        print(res)
        exit(1)

    return res

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
        f = model.cg_taxable_fraction(year)
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
            f = model.cg_taxable_fraction(year)
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

S = tomldata.Data()
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

if precheck_consistancy():
    model = lp.lp_constraint_model(S, vindx, taxtable, capgainstable, penalty, stded, SS_taxable, args.verbose)
    c, A, b = model.build_model()
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
