#!/usr/bin/python3

#
# A Retirement Planner (optimize withdrawals for most efficient use of the nest egg)
#

import time
import argparse
import scipy.optimize
import taxinfo as tif
import tomldata
import vector_var_index as vvar
import app_output as app_out
import lp_constraint_model as lp
import modelio

__version__ = '0.3-rc2'


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
            print("year: %d, total contributions of (%.0f) to all Retirement accounts exceeds other earned income (%.0f)" % (
                year, t, S.income[year]))
            print(
                "Please change the contributions in the toml file to be less than non-SS income.")
            exit(1)
    return True


def consistancy_check(res, years, taxbins, cgbins, accounts, accmap, vindx):
    # check to see if the ordinary tax brackets are filled in properly
    print()
    print()
    print("Consistancy Checking:")
    print()

    result = vvar.my_check_index_sequence(
        years, taxbins, cgbins, accounts, accmap, vindx)

    for year in range(S.numyr):
        s = 0
        fz = False
        fnf = False
        i_mul = S.i_rate ** (S.preplanyears + year)
        for k in range(len(taxinfo.taxtable)):
            cut, size, rate, base = taxinfo.taxtable[k]
            size *= i_mul
            s += res.x[vindx.x(year, k)]
            if fnf and res.x[vindx.x(year, k)] > 0:
                print("Inproper packed brackets in year %d, bracket %d not empty while previous bracket not full." % (
                    year, k))
            if res.x[vindx.x(year, k)] + 1 < size:
                fnf = True
            if fz and res.x[vindx.x(year, k)] > 0:
                print("Inproperly packed tax brackets in year %d bracket %d" % (year, k))
            if res.x[vindx.x(year, k)] == 0.0:
                fz = True
        if S.accmap['aftertax'] > 0:
            scg = 0
            fz = False
            fnf = False
            for l in range(len(taxinfo.capgainstable)):
                cut, size, rate = taxinfo.capgainstable[l]
                size *= i_mul
                bamount = res.x[vindx.y(year, l)]
                scg += bamount
                for k in range(len(taxinfo.taxtable) - 1):
                    if taxinfo.taxtable[k][0] >= taxinfo.capgainstable[l][0] and taxinfo.taxtable[k][0] < taxinfo.capgainstable[l + 1][0]:
                        bamount += res.x[vindx.x(year, k)]
                if fnf and bamount > 0:
                    print("Inproper packed CG brackets in year %d, bracket %d not empty while previous bracket not full." % (
                        year, l))
                if bamount + 1 < size:
                    fnf = True
                if fz and bamount > 0:
                    print(
                        "Inproperly packed GC tax brackets in year %d bracket %d" % (year, l))
                if bamount == 0.0:
                    fz = True
        TaxableOrdinary = OrdinaryTaxable(year)
        if (TaxableOrdinary + 0.1 < s) or (TaxableOrdinary - 0.1 > s):
            print("Error: Expected (age:%d) Taxable Ordinary income %6.2f doesn't match bracket sum %6.2f" %
                  (year + S.startage, TaxableOrdinary, s))

        for j in range(len(S.accounttable)):
            a = res.x[vindx.b(year + 1, j)] - (res.x[vindx.b(year, j)] - res.x[vindx.w(
                year, j)] + deposit_amount(S, res, year, j)) * S.accounttable[j]['rate']
            if a > 1:
                v = S.accounttable[j]
                print("account[%d], type %s, index %d, mykey %s" %
                      (j, v['acctype'], v['index'], v['mykey']))
                print("account[%d] year to year balance NOT OK years %d to %d" % (
                    j, year, year + 1))
                print("difference is", a)

        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        if spendable + 0.1 < res.x[vindx.s(year)] or spendable - 0.1 > res.x[vindx.s(year)]:
            print("Calc Spendable %6.2f should equal s(year:%d) %6.2f" %
                  (spendable, year, res.x[vindx.s(year)]))
            for j in range(len(S.accounttable)):
                print("+w[%d,%d]: %6.0f" % (year, j, res.x[vindx.w(year, j)]))
                print("-D[%d,%d]: %6.0f" %
                      (year, j, deposit_amount(S, res, year, j)))
            print("+o[%d]: %6.0f +SS[%d]: %6.0f -tax: %6.0f -cg_tax: %6.0f" %
                  (year, S.income[year], year, S.SS[year], tax, cg_tax))

        bt = 0
        for k in range(len(taxinfo.taxtable)):
            bt += res.x[vindx.x(year, k)] * taxinfo.taxtable[k][2]
        if tax + 0.1 < bt or tax - 0.1 > bt:
            print("Calc tax %6.2f should equal brackettax(bt)[]: %6.2f" % (tax, bt))
    print()


def print_model_results(res):
    def printheader1(fieldwidth):
        names = None
        if S.secondary != "":
            names = "{}/{}\n".format(S.primary, S.secondary)
            age_width = 8
        else:
            if S.primary != 'nokey':
                names = "{}\n".format(S.primary)
            age_width = 5
        if names is not None:
            ao.output('{:<s}'.format(names, width=2 *
                                     age_width, use=2 * age_width))
        ao.output("{:>{width}.{width}s}".format('age ', width=age_width))
        headers = ["fIRA", "tIRA", "RMDref", "fRoth", "tRoth", "fAftaTx",
                   "tAftaTx", "o_inc", "SS", "Expense", "TFedTax", "Spndble"]
        for s in headers:
            ao.output("&@{:>{width}.{width}s}".format(s, width=fieldwidth))
        ao.output('\n')

    ao.output("\nActivity Summary:\n")
    ao.output('\n')
    fieldwidth = 7
    printheader1(fieldwidth)
    for year in range(S.numyr):
        i_mul = S.i_rate ** (S.preplanyears + year)
        age = year + S.startage
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)

        rmdref = 0
        # at most the first two accounts are type IRA w/ RMD requirement
        for j in range(min(2, len(S.accounttable))):
            if S.accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year, S.accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref += res.x[vindx.b(year, j)] / rmd

        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        deposit = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(S.accounttable)):
            withdrawal[S.accounttable[j]['acctype']] += res.x[vindx.w(year, j)]
            deposit[S.accounttable[j]['acctype']
                    ] += deposit_amount(S, res, year, j)

        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        items = [withdrawal['IRA'] / OneK, deposit['IRA'] / OneK, rmdref / OneK,  # IRA
                 withdrawal['roth'] / OneK, deposit['roth'] / OneK,  # Roth
                 withdrawal['aftertax'] / \
                 OneK, deposit['aftertax'] / OneK,  # D, # AftaTax
                 S.income[year] / OneK, S.SS[year] / \
                 OneK, S.expenses[year] / OneK,
                 (tax + cg_tax + earlytax) / OneK]
        for i in items:
            ao.output("&@{:>{width}.0f}".format(i, width=fieldwidth))
        s = res.x[vindx.s(year)] / OneK
        star = ' '
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        if spendable + 0.1 < res.x[vindx.s(year)] or \
                spendable - 0.1 > res.x[vindx.s(year)]:
            s = spendable / OneK
            star = '*'
        ao.output("&@%7.0f%c" % (s, star))
        ao.output("\n")
    printheader1(fieldwidth)


def print_income_expense_details():
    def print_income_header(headerlist, map, income_cat, fieldwidth):
        names = ''
        if S.secondary != "":
            names = "{}/{}".format(S.primary, S.secondary)
            age_width = 8
        else:
            if S.primary != 'nokey':
                names = "{}".format(S.primary)
            age_width = 5
        ao.output('{:<{width}.{use}s}'.format(
            names, width=age_width, use=age_width))
        for i in range(len(map)):
            if map[i] > 0:
                ats = 1
                if i > 0:
                    ats = map[i - 1]
                totalspace = fieldwidth * \
                    map[i] + map[i] - 1  # -1 is for the &
                ao.output("&{at:@<{at_width}.{at_width}s}{str:<{width}.{width}s}".format(
                    str=income_cat[i], width=totalspace, at='@', at_width=ats))
        ao.output("\n")
        ao.output("{str:>{width}s}".format(width=age_width, str='age '))
        for str in headerlist:
            if str == 'nokey':  # HAACCKKK
                str = 'SS'
            ao.output('&@{:>{width}.{width}s}'.format(str, width=fieldwidth))
        ao.output("\n")

    ao.output("\nIncome and Expense Summary:\n\n")
    headerlist, map, datamatrix = S.get_SS_income_asset_expense_list()
    income_cat = ['SSincome:', 'Income:', 'AssetSale:', 'Expense:']
    fieldwidth = 8
    print_income_header(headerlist, map, income_cat, fieldwidth)

    for year in range(S.numyr):
        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        for i in range(len(datamatrix)):
            ao.output("&@{:{width}.0f}".format(
                datamatrix[i][year] / OneK, width=fieldwidth))
        ao.output("\n")
    print_income_header(headerlist, map, income_cat, fieldwidth)


def deposit_amount(S, res, year, index):
    amount = res.x[vindx.D(year, index)]
    if S.accounttable[index]['acctype'] == 'aftertax':
        amount += S.asset_sale[year]
    return amount


def print_account_trans(res):
    def print_acc_header1():
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        if S.accmap['IRA'] > 1:
            ao.output(("&@%7s" * 8) % ("IRA1", "fIRA1", "tIRA1",
                                       "RMDref1", "IRA2", "fIRA2", "tIRA2", "RMDref2"))
        elif S.accmap['IRA'] == 1:
            ao.output(("&@%7s" * 4) % ("IRA", "fIRA", "tIRA", "RMDref"))
        if S.accmap['roth'] > 1:
            ao.output(("&@%7s" * 6) % ("Roth1", "fRoth1",
                                       "tRoth1", "Roth2", "fRoth2", "tRoth2"))
        elif S.accmap['roth'] == 1:
            ao.output(("&@%7s" * 3) % ("Roth", "fRoth", "tRoth"))
        if S.accmap['IRA'] + S.accmap['roth'] == len(S.accounttable) - 1:
            ao.output(("&@%7s" * 3) % ("AftaTx", "fAftaTx", "tAftaTx"))
        ao.output("\n")

    ao.output("\nAccount Transactions Summary:\n\n")
    print_acc_header1()
    #
    # Print pre-plan info
    #
    if S.secondary != "":
        ao.output("%3d/%3d:" % (S.primAge, S.primAge - S.delta))
    else:
        ao.output(" %3d:" % (S.primAge))
    for i in range(S.accmap['IRA']):
        ao.output(("&@%7.0f" * 4) % (
            S.accounttable[i]['origbal'] / OneK, 0, S.accounttable[i]['contrib'] / OneK, 0))  # IRAn
    for i in range(S.accmap['roth']):
        index = S.accmap['IRA'] + i
        ao.output(("&@%7.0f" * 3) % (
            S.accounttable[index]['origbal'] / OneK, 0, S.accounttable[index]['contrib'] / OneK))  # rothn
    index = S.accmap['IRA'] + S.accmap['roth']
    if index == len(S.accounttable) - 1:
        ao.output(("&@%7.0f" * 3) % (
            S.accounttable[index]['origbal'] / OneK, 0, S.accounttable[index]['contrib'] / OneK))  # aftertax
    ao.output("\n")
    ao.output("Plan Start: ---------\n")
    #
    # Print plan info for each year
    # TODO clean up the if/else below to follow the above forloop pattern
    #
    for year in range(S.numyr):
        rmdref = [0, 0]
        # only first two accounts are type IRA w/ RMD
        for j in range(min(2, len(S.accounttable))):
            if S.accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year, S.accounttable[j]['mykey'])
                if rmd > 0:
                    rmdref[j] = res.x[vindx.b(year, j)] / rmd

        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        if S.accmap['IRA'] > 1:
            ao.output(("&@%7.0f" * 8) % (
                res.x[vindx.b(year, 0)] / OneK, res.x[vindx.w(year, 0)] /
                OneK, deposit_amount(S, res, year, 0) /
                OneK, rmdref[0] / OneK,  # IRA1
                res.x[vindx.b(year, 1)] / OneK, res.x[vindx.w(year, 1)] / OneK, deposit_amount(S, res, year, 1) / OneK, rmdref[1] / OneK))  # IRA2
        elif S.accmap['IRA'] == 1:
            ao.output(("&@%7.0f" * 4) % (
                res.x[vindx.b(year, 0)] / OneK, res.x[vindx.w(year, 0)] / OneK, deposit_amount(S, res, year, 0) / OneK, rmdref[0] / OneK))  # IRA1
        index = S.accmap['IRA']
        if S.accmap['roth'] > 1:
            ao.output(("&@%7.0f" * 6) % (
                res.x[vindx.b(year, index)] / OneK, res.x[vindx.w(year, index)] /
                OneK, deposit_amount(S, res, year, index) / OneK,  # roth1
                res.x[vindx.b(year, index + 1)] / OneK, res.x[vindx.w(year, index + 1)] / OneK, deposit_amount(S, res, year, index + 1) / OneK))  # roth2
        elif S.accmap['roth'] == 1:
            ao.output(("&@%7.0f" * 3) % (
                res.x[vindx.b(year, index)] / OneK, res.x[vindx.w(year, index)] / OneK, deposit_amount(S, res, year, index) / OneK))  # roth1
        index = S.accmap['IRA'] + S.accmap['roth']
        #assert index == len(S.accounttable)-1
        if index == len(S.accounttable) - 1:
            ao.output(("&@%7.0f" * 3) % (
                res.x[vindx.b(year, index)] / OneK,
                res.x[vindx.w(year, index)] / OneK,
                deposit_amount(S, res, year, index) / OneK))  # aftertax account
        ao.output("\n")
    ao.output("Plan End: -----------\n")
    #
    # Post plan info
    #
    year = S.numyr
    if S.secondary != "":
        ao.output("%3d/%3d:" %
                  (year + S.startage, S.numyr + S.startage - S.delta))
    else:
        ao.output(" %3d:" % (year + S.startage))
    for i in range(S.accmap['IRA']):
        ao.output(("&@%7.0f" * 4) % (
            res.x[vindx.b(year, i)] / OneK, 0, 0, 0))  # IRAn
    for i in range(S.accmap['roth']):
        index = S.accmap['IRA'] + i
        ao.output(("&@%7.0f" * 3) % (
            res.x[vindx.b(year, index)] / OneK, 0, 0))  # rothn
    index = S.accmap['IRA'] + S.accmap['roth']
    if index == len(S.accounttable) - 1:
        ao.output(("&@%7.0f" * 3) % (
            res.x[vindx.b(year, index)] / OneK, 0, 0))  # aftertax
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
        ao.output(("&@%7s" * 15) %
                  ("fIRA", "tIRA", "TxbleO", "TxbleSS", "deduct", "T_inc", "earlyP", "fedtax", "mTaxB%", "fAftaTx", "tAftaTx", "cgTax%", "cgTax", "TFedTax", "spndble"))
        ao.output("\n")

    ao.output("\nTax Summary:\n\n")
    printheader_tax()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** (S.preplanyears + year)
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        f = model.cg_taxable_fraction(year)
        ttax = tax + cg_tax + earlytax
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        deposit = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(S.accounttable)):
            withdrawal[S.accounttable[j]['acctype']] += res.x[vindx.w(year, j)]
            deposit[S.accounttable[j]['acctype']
                    ] += deposit_amount(S, res, year, j)
        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        star = ' '
        if rothearly:
            star = '*'
        ao.output(("&@%7.0f" * 6 + "&@%6.0f%c" * 1 + "&@%7.0f" * 8) %
                  (withdrawal['IRA'] / OneK, deposit['IRA'] / OneK,  # sum IRA
                   S.taxed[year] / OneK, taxinfo.SS_taxable * \
                   S.SS[year] / OneK,
                   taxinfo.stded * i_mul / OneK, T / OneK, earlytax / \
                   OneK, star, tax / OneK, rate * 100,
                   withdrawal['aftertax'] / \
                   OneK, deposit['aftertax'] / OneK,  # Aftertax
                   f * 100, cg_tax / OneK,
                   ttax / OneK, res.x[vindx.s(year)] / OneK))
        ao.output("\n")
    printheader_tax()


def print_tax_brackets(res):
    def printheader_tax_brackets():
        if S.secondary != "":
            #ao.output("@@@@@@@%64s" % "Marginal Rate(%):")
            spaces = 47
        else:
            #ao.output("@@@@@@@%61s" % "Marginal Rate(%):")
            spaces = 44
        ao.output("{amp:&<{amp_width}.{amp_width}s}{at:@<{at_width}.{at_width}s}{str:<{width}.{width}s}".format(
            str="Marginal Rate(%):", width=17, amp='&', amp_width=spaces, at='@', at_width=7))
        for k in range(len(taxinfo.taxtable)):
            (cut, size, rate, base) = taxinfo.taxtable[k]
            ao.output("&@%6.0f" % (rate * 100))
        ao.output("\n")
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        ao.output(("&@%7s" * 7) % ("fIRA", "tIRA", "TxbleO",
                                   "TxbleSS", "deduct", "T_inc", "fedtax"))
        for k in range(len(taxinfo.taxtable)):
            ao.output("&@brckt%d" % k)
        ao.output("&@brkTot\n")

    ao.output("\nOverall Tax Bracket Summary:\n")
    printheader_tax_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** (S.preplanyears + year)
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        ttax = tax + cg_tax
        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        withdrawal = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        deposit = {'IRA': 0, 'roth': 0, 'aftertax': 0}
        for j in range(len(S.accounttable)):
            withdrawal[S.accounttable[j]['acctype']] += res.x[vindx.w(year, j)]
            deposit[S.accounttable[j]['acctype']
                    ] += deposit_amount(S, res, year, j)
        ao.output(("&@%7.0f" * 7) %
                  (
            withdrawal['IRA'] / OneK, deposit['IRA'] / OneK,  # IRA
            S.taxed[year] / OneK, taxinfo.SS_taxable * S.SS[year] / OneK,
            taxinfo.stded * i_mul / OneK, T / OneK, tax / OneK))
        bt = 0
        for k in range(len(taxinfo.taxtable)):
            ao.output("&@%6.0f" % res.x[vindx.x(year, k)])
            bt += res.x[vindx.x(year, k)]
        ao.output("&@%6.0f\n" % bt)
    printheader_tax_brackets()


def print_cap_gains_brackets(res):
    def printheader_capgains_brackets():
        if S.secondary != "":
            spaces = 39
        else:
            spaces = 36
        ao.output("{amp:&<{amp_width}.{amp_width}s}{at:@<{at_width}.{at_width}s}{str:<{width}.{width}s}".format(
            str="Marginal Rate(%):", width=17, amp='&', amp_width=spaces, at='@', at_width=6))
        for l in range(len(taxinfo.capgainstable)):
            (cut, size, rate) = taxinfo.capgainstable[l]
            ao.output("&@%6.0f" % (rate * 100))
        ao.output("\n")
        if S.secondary != "":
            ao.output("%s/%s\n" % (S.primary, S.secondary))
            ao.output("    age ")
        else:
            if S.primary != 'nokey':
                ao.output("%s\n" % (S.primary))
            ao.output(" age ")
        ao.output(("&@%7s" * 6) % ("fAftaTx", "tAftaTx",
                                   "cgTax%", "cgTaxbl", "T_inc", "cgTax"))
        for l in range(len(taxinfo.capgainstable)):
            ao.output("&@brckt%d" % l)
        ao.output("&@brkTot\n")

    ao.output("\nOverall Capital Gains Bracket Summary:\n")
    printheader_capgains_brackets()
    for year in range(S.numyr):
        age = year + S.startage
        i_mul = S.i_rate ** (S.preplanyears + year)
        f = 1
        atw = 0
        atd = 0
        att = 0
        if S.accmap['aftertax'] > 0:
            f = model.cg_taxable_fraction(year)
            # Aftertax / investment account always the last entry when present
            j = len(S.accounttable) - 1
            # Aftertax / investment account
            atw = res.x[vindx.w(year, j)] / OneK
            # Aftertax / investment account
            atd = deposit_amount(S, res, year, j) / OneK
            #
            # OK, this next bit can be confusing. In the line above atd
            # includes both the D(i,j) and net amount from sell of assets
            # like homes or real estate. But the sale of these illiquid assets
            # does not use the aftertax account basis. They have been handled
            # separately in S.cg_asset_taxed. Given this we only ad to
            # cg_taxable the withdrawals over deposits, as is normal, plus
            # the taxable amounts from asset sales.
            att = ((f * (res.x[vindx.w(year, j)] - res.x[vindx.D(year, j)])) +
                   S.cg_asset_taxed[year]) / OneK  # non-basis fraction / cg taxable $
            if atd > atw:
                # non-basis fraction / cg taxable $
                att = S.cg_asset_taxed[year] / OneK
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        ttax = tax + cg_tax
        if S.secondary != "":
            ao.output("%3d/%3d:" %
                      (year + S.startage, year + S.startage - S.delta))
        else:
            ao.output(" %3d:" % (year + S.startage))
        ao.output(("&@%7.0f" * 6) %
                  (
            atw, atd,  # Aftertax / investment account
            f * 100, att,  # non-basis fraction / cg taxable $
            T / OneK, cg_tax / OneK))
        bt = 0
        bttax = 0
        for l in range(len(taxinfo.capgainstable)):
            ty = 0
            if S.accmap['aftertax'] > 0:
                ty = res.x[vindx.y(year, l)]
            ao.output("&@%6.0f" % ty)
            bt += ty
            bttax += ty * taxinfo.capgainstable[l][2]
        ao.output("&@%6.0f\n" % bt)
        if args.verbosewga:
            print(" cg bracket ttax %6.0f " % bttax, end='')
            print("x->y[1]: %6.0f " % (res.x[vindx.x(year, 0)] +
                                       res.x[vindx.x(year, 1)]), end='')
            print("x->y[2]: %6.0f " % (res.x[vindx.x(year, 2)] + res.x[vindx.x(year, 3)
                                                                       ] + res.x[vindx.x(year, 4)] + res.x[vindx.x(year, 5)]), end='')
            print("x->y[3]: %6.0f" % res.x[vindx.x(year, 6)])
        # TODO move to consistancy_check()
        # if (taxinfo.capgainstable[0][1]*i_mul -(res.x[vindx.x(year,0)]+res.x[vindx.x(year,1)])) <= res.x[vindx.y(year,1)]:
        #    print("y[1]remain: %6.0f "% (taxinfo.capgainstable[0][1]*i_mul -(res.x[vindx.x(year,0)]+res.x[vindx.x(year,1)])))
        # if (taxinfo.capgainstable[1][1]*i_mul - (res.x[vindx.x(year,2)]+ res.x[vindx.x(year,3)]+ res.x[vindx.x(year,4)]+res.x[vindx.x(year,5)])) <= res.x[vindx.y(year,2)]:
        #    print("y[2]remain: %6.0f " % (taxinfo.capgainstable[1][1]*i_mul - (res.x[vindx.x(year,2)]+ res.x[vindx.x(year,3)]+ res.x[vindx.x(year,4)]+res.x[vindx.x(year,5)])))
    printheader_capgains_brackets()


def OrdinaryTaxable(year):
    withdrawals = 0
    deposits = 0
    for j in range(min(2, len(S.accounttable))):
        if S.accounttable[j]['acctype'] == 'IRA':
            withdrawals += res.x[vindx.w(year, j)]
            deposits += deposit_amount(S, res, year, j)
    T = withdrawals - deposits + S.taxed[year] + taxinfo.SS_taxable * \
        S.SS[year] - (taxinfo.stded * S.i_rate**(S.preplanyears + year))
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
    roth_early = False
    for j in range(len(S.accounttable)):
        if S.accounttable[j]['acctype'] != 'aftertax':
            if S.apply_early_penalty(year, S.accounttable[j]['mykey']):
                earlytax += res.x[vindx.w(year, j)] * taxinfo.penalty
                if res.x[vindx.w(year, j)] > 0 and S.accounttable[j]['acctype'] == 'roth':
                    roth_early = True
    T = OrdinaryTaxable(year)
    ntax = 0
    rate = 0
    for k in range(len(taxinfo.taxtable)):
        ntax += res.x[vindx.x(year, k)] * taxinfo.taxtable[k][2]
        if res.x[vindx.x(year, k)] > 0:
            rate = taxinfo.taxtable[k][2]
    tax = ntax
    D = 0
    ncg_tax = 0
    # if S.accmap['aftertax'] > 0:
    for j in range(len(S.accounttable)):
        D += deposit_amount(S, res, year, j)
    if S.accmap['aftertax'] > 0:
        for l in range(len(taxinfo.capgainstable)):
            ncg_tax += res.x[vindx.y(year, l)] * taxinfo.capgainstable[l][2]
    tot_withdrawals = 0
    for j in range(len(S.accounttable)):
        tot_withdrawals += res.x[vindx.w(year, j)]
    spendable = tot_withdrawals - D + \
        S.income[year] + S.SS[year] - S.expenses[year] - \
        tax - ncg_tax - earlytax + S.asset_sale[year]
    return T, spendable, tax, rate, ncg_tax, earlytax, roth_early


def get_result_totals(res):
    twithd = 0
    ttax = 0
    tcg_tax = 0
    tT = 0
    tearlytax = 0
    tincome = 0
    pv_tincome = 0
    tspendable = 0
    pv_twithd = 0
    pv_ttax = 0
    pv_tT = 0
    for year in range(S.numyr):
        i_mul = S.i_rate ** (S.preplanyears + year)
        T, spendable, tax, rate, cg_tax, earlytax, rothearly = IncomeSummary(
            year)
        tot_withdrawals = 0
        for j in range(len(S.accounttable)):
            tot_withdrawals += res.x[vindx.w(year, j)]
        twithd += tot_withdrawals
        tincome += S.income[year] + S.SS[year]  # + withdrawals
        ttax += tax
        tcg_tax += cg_tax
        tearlytax += earlytax
        tT += T
        tspendable += spendable
    tbeginbal = 0
    tendbal = 0
    for j in range(len(S.accounttable)):
        tbeginbal += res.x[vindx.b(0, j)]
        # balance for the year following the last year
        tendbal += res.x[vindx.b(S.numyr, j)]

    return twithd, tincome + twithd, tT, ttax, tcg_tax, tearlytax, tspendable, tbeginbal, tendbal


def print_base_config(res):
    totwithd, tincome, tTaxable, tincometax, tcg_tax, tearlytax, tspendable, tbeginbal, tendbal = get_result_totals(
        res)
    ao.output("\n")
    ao.output("======\n")
    ao.output("Optimized for {} with {} status\n\tstarting at age {} with an estate of ${:_.0f} liquid and ${:_.0f} illiquid\n".format(
        S.maximize, S.retirement_type, S.startage, tbeginbal, S.illiquidassetplanstart))
    ao.output('\n')
    ao.output('Minium desired: ${:0_.0f}\n'.format(S.min))
    ao.output('Maximum desired: ${:0_.0f}\n'.format(S.max))
    ao.output('\n')
    ao.output('After tax yearly income: ${:0_.0f} adjusting for inflation\n\tand final estate at age {} with ${:_.0f} liquid and ${:_.0f} illiquid\n'.format(
        res.x[vindx.s(0)], S.startage + S.numyr, tendbal, S.illiquidassetplanend))
    ao.output("\n")
    ao.output('total withdrawals: ${:0_.0f}\n'.format(totwithd))
    ao.output('total ordinary taxable income ${:_.0f}\n'.format(tTaxable))
    ao.output('total ordinary tax on all taxable income: ${:0_.0f} ({:.1f}%) of taxable income\n'.format(
        tincometax + tearlytax, 100 * (tincometax + tearlytax) / tTaxable))
    ao.output('total income (withdrawals + other) ${:_.0f}\n'.format(tincome))
    ao.output('total cap gains tax: ${:0_.0f}\n'.format(tcg_tax))
    ao.output('total all tax on all income: ${:0_.0f} ({:.1f}%)\n'.format(
        tincometax + tcg_tax + tearlytax, 100 * (tincometax + tcg_tax + tearlytax) / tincome))
    ao.output(
        "Total spendable (after tax money): ${:0_.0f}\n".format(tspendable))
    ao.output("\n")


def verifyInputs(c, A, b):
    m = len(A)
    n = len(A[0])
    if len(c) != n:
        print("lp: c vector incorrect length")
    if len(b) != m:
        print("lp: b vector incorrect length")

        # Do some sanity checks so that ab does not become singular during the
        # simplex solution. If the ZeroRow checks are removed then the code for
        # finding a set of linearly indepent columns must be improved.

        # Check that if a row of A only has zero elements that corresponding
        # element in b is zero, otherwise the problem is infeasible.
        # Otherwise return ErrZeroRow.
    zeroRows = 0
    for i in range(m):
        isZero = True
        for j in range(n):
            if A[i][j] != 0:
                isZero = False
                break
        if isZero and b[i] != 0:
            # Infeasible
            print("ErrInfeasible -- row[%d]\n" % i)
        elif isZero:
            zeroRows += 1
            print("ErrZeroRow -- row[%d]\n" % i)
    # Check that if a column only has zero elements that the respective C vector
    # is positive (otherwise unbounded). Otherwise return ErrZeroColumn.
    zeroColumns = 0
    for j in range(n):
        isZero = True
        for i in range(m):
            if A[i][j] != 0:
                isZero = False
                break
        if isZero and c[j] < 0:
            print("ErrUnbounded -- column[%d] %s\n" % (j, vindx.varstr(j)))
        elif isZero:
            zeroColumns += 1
            print("ErrZeroColumn -- column[%d] %s\n" % (j, vindx.varstr(j)))
    print("\nZero Rows: %d, Zero Columns: %d\n" % (zeroRows, zeroColumns))


# Program entry point
# Instantiate the parser
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Create an optimized finacial plan for retirement.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Extra output from solver")
    parser.add_argument('-A', '--alltables', action='store_true',
                        help="Output all plan tables (-va -vi -vt -vtb)")
    parser.add_argument('-va', '--verboseaccounttrans', action='store_true',
                        help="Output detailed account transactions from solver")
    parser.add_argument('-vi', '--verboseincome', action='store_true',
                        help="Output detailed list of income as specified in social security, income, asset and expense sections")
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
    parser.add_argument('-mdp', '--modeldumptable', nargs='?',
                        const='./RPlanModel.dat', default='',
                        help="Output the entire LP model as c, A, b to file MODELDUMPTABLE (default: ./RPlanModel.dat)")
    parser.add_argument('-mld', '--modelloadtable', nargs='?',
                        const='./RPlanModel.dat', default='',
                        help="Load the LP model as c, A, b from file MODELLOADTABLE (default: ./RPlanModel.dat)")
    parser.add_argument('-ts', '--timesimplex', action='store_true',
                        help="Measure and print the amount of time used by the simplex solver")
    parser.add_argument('-csv', '--csv', nargs='?', const='./a.csv', default='',
                        help="Additionally write the output to a csv file CVS (default: ./ .cvs)")
    parser.add_argument('-1k', '--noroundingoutput', action='store_true',
                        help="Do not round the output to thousands")
    parser.add_argument('-nd', '--notdrarothradeposits', action='store_true',
                        help="Do not allow deposits to TDRA or ROTHRA accounts beyond explicit contributions")
    parser.add_argument('-V', '--version', action='version', version='%(prog)s Version ' + __version__,
                        help="Display the program version number and exit")
    parser.add_argument(
        'conffile', help='Require configuration input toml file')
    args = parser.parse_args()

    if args.alltables:
        args.verboseaccounttrans = True
        args.verboseincome = True
        args.verbosetax = True
        args.verbosetaxbrackets = True

    csv_file_name = None
    if args.csv != '':
        csv_file_name = args.csv
    ao = app_out.app_output(csv_file_name)

    taxinfo = tif.taxinfo()
    S = tomldata.Data(taxinfo)
    S.load_toml_file(args.conffile)
    S.process_toml_info()

    #print("\naccounttable: ", S.accounttable)

    if S.accmap['IRA'] + S.accmap['roth'] + S.accmap['aftertax'] == 0:
        print('Error: This app optimizes the withdrawals from your retirement account(s); you must have at least one specified in the input toml file.')
        exit(0)

    if args.verbosewga:
        print("accounttable: ", S.accounttable)

    non_binding_only = True
    if args.verbosemodelall:
        non_binding_only = False

    OneK = 1000.0
    if args.noroundingoutput:
        OneK = 1

    years = S.numyr
    taxbins = len(taxinfo.taxtable)
    cgbins = len(taxinfo.capgainstable)
    accounts = len(S.accounttable)

    vindx = vvar.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)

    vid = [years, taxbins, cgbins, S.accmap["IRA"],
           S.accmap["roth"], S.accmap["aftertax"]]

    #print("Is modelDumpTable Set?")
    if args.modeldumptable != '':
        #print("ModelDumpTable set")
        print(args.modeldumptable)

    if precheck_consistancy():

        if args.modelloadtable == '':
            model = lp.lp_constraint_model(S, vindx, taxinfo.taxtable, taxinfo.capgainstable, taxinfo.penalty,
                                           taxinfo.stded, taxinfo.SS_taxable, args.verbose, args.notdrarothradeposits)
            c, A, b, notes = model.build_model()
            """
            if args.modeldumptable != '':
                #modelio.dumpModel(c, A, b)
                modelio.binDumpModel(c, A, b, None, args.modeldumptable)
            """
        else:
            print("Loadfile: ", args.modelloadtable)
            c, A, b, vid = modelio.binLoadModel(args.modelloadtable)
            note = None
        #verifyInputs( c , A , b )
        if args.timesimplex:
            t = time.process_time()
        res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                     options={"disp": args.verbose,
                                              #"bland": True,
                                              "tol": 1.0e-7,
                                              "maxiter": 4000})
        if args.timesimplex:
            elapsed_time = time.process_time() - t
            print("\nElapsed Simplex time: %s seconds" % elapsed_time)
        if args.modeldumptable != '':
            modelio.binDumpModel(c, A, b, res.x, vid,
                                 args.modeldumptable + "X")
        if args.verbosemodel or args.verbosemodelall:
            if res.success == False:
                model.print_model_matrix(c, A, b, notes, None, False)
                print(res)
                exit(1)
            else:
                model.print_model_matrix(
                    c, A, b, notes, res.slack, non_binding_only)
        if args.verbosewga or res.success == False:
            print(res)
            if res.success == False:
                exit(1)
        consistancy_check(res, years, taxbins, cgbins,
                          accounts, S.accmap, vindx)

        print_model_results(res)
        if args.verboseincome:
            print_income_expense_details()
        if args.verboseaccounttrans:
            print_account_trans(res)
        if args.verbosetax:
            print_tax(res)
        if args.verbosetaxbrackets:
            print_tax_brackets(res)
            print_cap_gains_brackets(res)
        print_base_config(res)
