
# Build model for:
# Minimize: c^T * x
# Subject to: A_ub * x <= b_ub
#all vars positiveA
def build_model(S, vindx, taxtable, capgainstable, penalty, stded, SS_taxable, args):

    nvars = vindx.vsize
    A = []
    b = []
    c = [0] * nvars

    #
    # Add objective function (S1') becomes (R1') if PlusEstate is added
    #
    for year in range(S.numyr):
        c[vindx.s(year)] = -1
    #
    # Add objective function tax bracket forcing function (EXPERIMENTAL)
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)):
            # multiplies the impact of higher brackets opposite to optimization
            # the intent here is to pressure higher brackets more and pack the 
            # lower brackets
            c[vindx.x(year,k)] = k/10 
    #
    # Adder objective function (R1') when PlusEstate is added
    #
    if S.maximize == "PlusEstate":
        for j in range(len(S.accounttable)):
            c[vindx.b(S.numyr,j)] = -1*S.accounttable[j]['estateTax'] # account discount rate
        print("\nConstructing Spending + Estate Model:\n")
    else:
        print("\nConstructing Spending Model:\n")
        startamount = 0
        for j in range(len(S.accounttable)):
            startamount += S.accounttable[j]['bal']
        balancer = 1/(startamount) 
        for j in range(len(S.accounttable)):
            c[vindx.b(S.numyr,j)] = -1*balancer *S.accounttable[j]['estateTax'] # balance and discount rate
    
    #
    # Add constraint (2')
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(S.accounttable)):
            p = 1
            if S.accounttable[j]['acctype'] != 'aftertax':
                if S.apply_early_penalty(year,S.accounttable[j]['mykey']):
                    p = 1-penalty
            row[vindx.w(year,j)] = -1*p 
        for k in range(len(taxtable)): 
            row[vindx.x(year,k)] = taxtable[k][2] # income tax
        if S.accmap['aftertax'] > 0:
            for l in range(len(capgainstable)): 
                row[vindx.y(year,l)] = capgainstable[l][2] # cap gains tax
            for j in range(len(S.accounttable)):
                row[vindx.D(year,j)] = 1
        row[vindx.s(year)] = 1
        A+=[row]
        b+=[S.income[year] + S.SS[year] - S.expenses[year]]
    #
    # Add constraint (3a')
    #
    #"""
    for year in range(S.numyr-1):
        row = [0] * nvars
        row[vindx.s(year+1)] = 1
        row[vindx.s(year)] = -1*S.i_rate
        A+=[row]
        b+=[0]
    #"""
    #
    # Add constraint (3b')
    #
    #"""
    for year in range(S.numyr-1):
        row = [0] * nvars
        row[vindx.s(year)] = S.i_rate
        row[vindx.s(year+1)] = -1
        A+=[row]
        b+=[0]
    #"""
    #
    # Add constrant (4') rows - not needed if [desired.income] is not defined in input
    #
    #"""
    if S.desired[0] != 0:
        for year in range(1): # Only needs setting at the beginning
            row = [0] * nvars
            row[vindx.s(year)] = -1
            A+=[row]
            b+=[ - S.desired[year] ]     # [- d_i]

    #
    # Add constraints for (5') rows - not added if [max.income] is not defined in input
    #
    if S.max[0] != 0:
        for year in range(1): # Only needs to be set at the beginning
            row = [0] * nvars
            row[vindx.s(year)] = 1
            A+=[row]
            b+=[ S.max[year] ]     # [ dm_i]

    #
    # Add constaints for (5+') rows
    #
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(S.accounttable)):
            if S.accounttable[j]['acctype'] != 'aftertax':
                row[vindx.D(year,j)] = 1
        A+=[row]
        b+=[min(S.income[year],S.maxContribution(year))] 
    #
    # Add constaints for (5++') rows
    #
    #"""
    for year in range(S.numyr):
        row = [0] * nvars
        for j in range(len(S.accounttable)):
            v = S.accounttable[j].get('contributions', None)     # ['acctype'] != 'aftertax':
            if v is not None: 
                if v[year] > 0:
                    row = [0] * nvars
                    row[vindx.D(year,j)] = -1
                    A+=[row]
                    b+=[-1*v[year]]
    #"""
    #
    # Add constaints for (6') rows
    #
    for year in range(S.numyr):
        for j in range(min(2,len(S.accounttable))): # at most the first two accounts are type IRA w/ RMD requirement
            if S.accounttable[j]['acctype'] == 'IRA':
                rmd = S.rmd_needed(year,S.accounttable[j]['mykey'])
                if rmd > 0:
                    row = [0] * nvars
                    row[vindx.b(year,j)] = 1/rmd 
                    row[vindx.w(year,j)] = -1
                    A+=[row]
                    b+=[0]

    #"""
    #
    # Add constraints for (7a')
    #
    """
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for k in range(len(taxtable)):
            row[vindx.x(year,k)] = 1
        for j in range(min(2,len(S.accounttable))): # IRA can only be in the first two accounts
            if S.accounttable[j]['acctype'] == 'IRA':
                row[vindx.w(year,j)] = -1 # Account 0 is TDRA
        A+=[row]
        b+=[S.taxed[year]+SS_taxable*S.SS[year]-stded*adj_inf]
    """
    #
    # Add constraints for (7b')
    #
    for year in range(S.numyr):
        adj_inf = S.i_rate**year
        row = [0] * nvars
        for j in range(min(2,len(S.accounttable))): # IRA can only be in the first two accounts
            if S.accounttable[j]['acctype'] == 'IRA':
                row[vindx.w(year,j)] = 1 # Account 0 is TDRA
        for k in range(len(taxtable)):
            row[vindx.x(year,k)] = -1
        A+=[row]
        b+=[stded*adj_inf-S.taxed[year]-SS_taxable*S.SS[year]]
    #
    # Add constraints for (8')
    #
    for year in range(S.numyr):
        for k in range(len(taxtable)-1):
            row = [0] * nvars
            row[vindx.x(year,k)] = 1
            A+=[row]
            b+=[(taxtable[k][1])*(S.i_rate**year)] # inflation adjusted
    #
    # Add constraints for (9a')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            f = cg_taxable_fraction(S, year)
            row = [0] * nvars
            for l in range(len(capgainstable)):
                row[vindx.y(year,l)] = 1
            j = len(S.accounttable)-1
            row[vindx.w(year,j)] = -1*f # last Account is investment / stocks
            A+=[row]
            b+=[0]
    #
    # Add constraints for (9b')
    #
    if S.accmap['aftertax'] > 0:
        for year in range(S.numyr):
            f = cg_taxable_fraction(S, year)
            row = [0] * nvars
            j = len(S.accounttable)-1
            row[vindx.w(year,j)] = f # last Account is investment / stocks
            for l in range(len(capgainstable)):
                row[vindx.y(year,l)] = -1
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
                row[vindx.y(year,l)] = 1
                for k in range(len(taxtable)-1):
                    if taxtable[k][0] >= capgainstable[l][0] and taxtable[k][0] < capgainstable[l+1][0]:
                        row[vindx.x(year,k)] = 1
                A+=[row]
                b+=[capgainstable[l][1]*adj_inf] # mcg[i,l] inflation adjusted
                #print_constraint( row, capgainstable[l][1]*adj_inf)
    #
    # Add constraints for (11a')
    #
    """
    aftertax = 0
    if S.accmap['aftertax'] > 0:
        aftertax = 1
    for year in range(S.numyr): 
        for j in range(len(S.accounttable)-aftertax): # for all accounts except aftertax
            row = [0] * nvars
            row[vindx.b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[vindx.b(year,j)] = -1*S.accounttable[j]['rate']
            row[vindx.w(year,j)] = S.accounttable[j]['rate']
            A+=[row]
            b+=[0]
    #
    # Add constraints for (11b')
    #
    
    aftertax = 0
    if S.accmap['aftertax'] > 0:
        aftertax = 1
    for year in range(S.numyr):
        for j in range(len(S.accounttable)-aftertax): # for all accounts except aftertax
            row = [0] * nvars
            row[vindx.b(year,j)] = S.accounttable[j]['rate']
            row[vindx.w(year,j)] = -1*S.accounttable[j]['rate']
            row[vindx.b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #"""
    #
    # Add constraints for (12a')
    #
    #if S.accmap['aftertax'] > 0:
    for year in range(S.numyr): 
        for j in range(len(S.accounttable)): # for all accounts 
            #j = len(S.accounttable)-1 # nl the last account, the investment account
            row = [0] * nvars
            row[vindx.b(year+1,j)] = 1 ### b[i,j] supports an extra year
            row[vindx.b(year,j)] = -1*S.accounttable[j]['rate']
            row[vindx.w(year,j)] = S.accounttable[j]['rate']
            row[vindx.D(year,j)] = -1*S.accounttable[j]['rate']
            A+=[row]
            b+=[0]
    #
    # Add constraints for (12b')
    #
    #if S.accmap['aftertax'] > 0:
    for year in range(S.numyr):
        for j in range(len(S.accounttable)): # for all accounts 
            #j = len(S.accounttable)-1 # nl the last account, the investment account
            row = [0] * nvars
            row[vindx.b(year,j)] = S.accounttable[j]['rate']
            row[vindx.w(year,j)] = -1*S.accounttable[j]['rate']
            row[vindx.D(year,j)] = S.accounttable[j]['rate']
            row[vindx.b(year+1,j)] = -1  ### b[i,j] supports an extra year
            A+=[row]
            b+=[0]
    #
    # Constraint for (13a')
    #   Set the begining b[1,j] balances
    #
    for j in range(len(S.accounttable)):
        row = [0] * nvars
        row[vindx.b(0,j)] = 1
        A+=[row]
        b+=[S.accounttable[j]['bal']]
    #
    # Constraint for (13b')
    #   Set the begining b[1,j] balances
    #
    for j in range(len(S.accounttable)):
        row = [0] * nvars
        row[vindx.b(0,j)] = -1
        A+=[row]
        b+=[-1*S.accounttable[j]['bal']]
    #
    # Constrant for (14') is default for sycpy so no code is needed
    #
    if args.verbose:
        print("Num vars: ", len(c))
        print("Num contraints: ", len(b))
        print()

    return c, A, b


def cg_taxable_fraction(S, year):
    f = 1
    if S.accmap['aftertax'] > 0:
        for v in S.accounttable:
            if v['acctype'] == 'aftertax':
                f = 1 - (v['basis']/(v['bal']*v['rate']**year))
                break # should be the last entry anyway but...
    #f = 1 - (S.aftertax['basis']/(S.aftertax['bal']*S.aftertax['rate']**year))
    return f