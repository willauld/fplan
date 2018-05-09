
class lp_constraint_model:
    def __init__(self, S, vindx, taxtable, capgainstable, penalty, stded, SS_taxable, verbose, no_TDRA_ROTHRA_DEPOSITS):
        self.S = S
        self.var_index = vindx
        self.taxtable = taxtable
        self.cgtaxtable = capgainstable
        self.penalty = penalty
        self.stded = stded
        self.ss_taxable = SS_taxable
        self.verbose = verbose
        self.noTdraRothraDeposits = no_TDRA_ROTHRA_DEPOSITS

    # Build model for:
    # Minimize: c^T * x
    # Subject to: A_ub * x <= b_ub
    # all vars positiveA
    def build_model(self):

        # TODO integrate the following assignments into the code and remove them
        S = self.S
        vindx = self.var_index
        taxtable = self.taxtable
        capgainstable = self.cgtaxtable
        penalty = self.penalty
        stded = self.stded
        SS_taxable = self.ss_taxable

        nvars = vindx.vsize
        A = []
        b = []
        c = [0] * nvars
        notes = []

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
                c[vindx.x(year, k)] = k / 10
        #
        # Adder objective function (R1') when PlusEstate is added
        #
        if S.maximize == "PlusEstate":
            for j in range(len(S.accounttable)):
                # account discount rate
                c[vindx.b(S.numyr, j)] = -1 * S.accounttable[j]['estateTax']
            print("\nConstructing Spending + Estate Model:\n")
        else:
            print("\nConstructing Spending Model:\n")
            balancer = 0.001
            for j in range(len(S.accounttable)):
                # balance and discount rate
                c[vindx.b(S.numyr, j)] = -1 * balancer * \
                    S.accounttable[j]['estateTax']

        #
        # Add constraint (2')
        #
        notes += [{"index": len(A), "note": "Constraints 2':"}]
        for year in range(S.numyr):
            row = [0] * nvars
            for j in range(len(S.accounttable)):
                p = 1
                if S.accounttable[j]['acctype'] != 'aftertax':
                    if S.apply_early_penalty(year, S.accounttable[j]['mykey']):
                        p = 1 - penalty
                row[vindx.w(year, j)] = -1 * p
            for k in range(len(taxtable)):
                row[vindx.x(year, k)] = taxtable[k][2]  # income tax
            if S.accmap['aftertax'] > 0:
                for l in range(len(capgainstable)):
                    # cap gains tax
                    row[vindx.y(year, l)] = capgainstable[l][2]
                for j in range(len(S.accounttable)):
                    row[vindx.D(year, j)] = 1
            row[vindx.s(year)] = 1
            A += [row]
            b += [S.income[year] + S.SS[year] - S.expenses[year]]
        #
        # Add constraint (3a')
        #
        #"""
        notes += [{"index": len(A), "note": "Constraints 3a':"}]
        for year in range(S.numyr - 1):
            row = [0] * nvars
            row[vindx.s(year + 1)] = 1
            row[vindx.s(year)] = -1 * S.i_rate
            A += [row]
            b += [0]
        #"""
        #
        # Add constraint (3b')
        #
        #"""
        notes += [{"index": len(A), "note": "Constraints 3b':"}]
        for year in range(S.numyr - 1):
            row = [0] * nvars
            row[vindx.s(year)] = S.i_rate
            row[vindx.s(year + 1)] = -1
            A += [row]
            b += [0]
        #"""
        #
        # Add constrant (4') rows - not needed if [desired.income] is not defined in input
        #
        #"""
        notes += [{"index": len(A), "note": "Constraints 4':"}]
        if S.min != 0:
            for year in range(1):  # Only needs setting at the beginning
                row = [0] * nvars
                row[vindx.s(year)] = -1
                A += [row]
                b += [- S.min]     # [- d_i]

        #
        # Add constraints for (5') rows - not added if [max.income] is not defined in input
        #
        notes += [{"index": len(A), "note": "Constraints 5':"}]
        if S.max != 0:
            for year in range(1):  # Only needs to be set at the beginning
                row = [0] * nvars
                row[vindx.s(year)] = 1
                A += [row]
                b += [S.max]     # [ dm_i]

        #
        # Add constaints for (6') rows
        #
        #"""
        notes += [{"index": len(A), "note": "Constraints 6':"}]
        for year in range(S.numyr):
            row = [0] * nvars
            for j in range(len(S.accounttable)):
                if S.accounttable[j]['acctype'] != 'aftertax':
                    row[vindx.D(year, j)] = 1
            A += [row]
            # b+=[min(S.income[year],S.maxContribution(year,None))]
            # using S.taxed rather than S.income because income could
            # include non-taxed anueities that don't count.
            b += [min(S.taxed[year], S.maxContribution(year, None))]
        #
        # Add constaints for (7') rows
        #
        #"""
        notes += [{"index": len(A), "note": "Constraints 7':"}]
        for year in range(S.numyr):  # TODO this is not needed when there is only one retiree
            for v in S.retiree:
                row = [0] * nvars
                for j in range(len(S.accounttable)):
                    # ['acctype'] != 'aftertax': no 'mykey' in aftertax (this will either break or just not match - we will see)
                    if v['mykey'] == S.accounttable[j]['mykey']:
                        row[vindx.D(year, j)] = 1
                A += [row]
                b += [S.maxContribution(year, v['mykey'])]
        #"""
        #
        # Add constaints for (8') rows
        #
        notes += [{"index": len(A), "note": "Constraints 8':"}]
        for year in range(S.numyr):
            for j in range(len(S.accounttable)):
                v = S.accounttable[j].get('contributions', None)
                if v is not None:
                    if v[year] > 0:
                        row = [0] * nvars
                        row[vindx.D(year, j)] = -1
                        A += [row]
                        b += [-1 * v[year]]
        #
        # Add constaints for (9') rows
        #
        notes += [{"index": len(A), "note": "Constraints 9':"}]
        for year in range(S.numyr):
            # at most the first two accounts are type IRA w/ RMD requirement
            for j in range(min(2, len(S.accounttable))):
                if S.accounttable[j]['acctype'] == 'IRA':
                    ownerage = S.account_owner_age(year, S.accounttable[j])
                    if ownerage >= 70:
                        row = [0] * nvars
                        row[vindx.D(year, j)] = 1
                        A += [row]
                        b += [0]
        #
        # Add constaints for (N') rows
        #
        notes += [{"index": len(A), "note": "Constraints N':"}]
        if self.noTdraRothraDeposits:
            for year in range(S.numyr):
                for j in range(len(S.accounttable)):
                    v = S.accounttable[j].get('contributions', None)
                    max = 0
                    if v is not None:
                        max = v[year]
                    if S.accounttable[j]['acctype'] != 'aftertax':
                        row = [0] * nvars
                        row[vindx.D(year, j)] = 1
                        A += [row]
                        b += [max]
        #
        # Add constaints for (10') rows
        #
        notes += [{"index": len(A), "note": "Constraints 10':"}]
        for year in range(S.numyr):
            # at most the first two accounts are type IRA w/ RMD requirement
            for j in range(min(2, len(S.accounttable))):
                if S.accounttable[j]['acctype'] == 'IRA':
                    rmd = S.rmd_needed(year, S.accounttable[j]['mykey'])
                    if rmd > 0:
                        row = [0] * nvars
                        row[vindx.b(year, j)] = 1 / rmd
                        row[vindx.w(year, j)] = -1
                        A += [row]
                        b += [0]

        #
        # Add constraints for (11')
        #
        notes += [{"index": len(A), "note": "Constraints 11':"}]
        for year in range(S.numyr):
            adj_inf = S.i_rate**(S.preplanyears + year)
            row = [0] * nvars
            # IRA can only be in the first two accounts
            for j in range(min(2, len(S.accounttable))):
                if S.accounttable[j]['acctype'] == 'IRA':
                    row[vindx.w(year, j)] = 1  # Account 0 is TDRA
                    row[vindx.D(year, j)] = -1  # Account 0 is TDRA
            for k in range(len(taxtable)):
                row[vindx.x(year, k)] = -1
            A += [row]
            b += [stded * adj_inf - S.taxed[year] - SS_taxable * S.SS[year]]
        #
        # Add constraints for (12')
        #
        notes += [{"index": len(A), "note": "Constraints 12':"}]
        for year in range(S.numyr):
            for k in range(len(taxtable) - 1):
                row = [0] * nvars
                row[vindx.x(year, k)] = 1
                A += [row]
                # inflation adjusted
                b += [(taxtable[k][1]) * (S.i_rate**(S.preplanyears + year))]
        #
        # Add constraints for (13a')
        #
        notes += [{"index": len(A), "note": "Constraints 13a':"}]
        if S.accmap['aftertax'] > 0:
            for year in range(S.numyr):
                f = self.cg_taxable_fraction(year)
                row = [0] * nvars
                for l in range(len(capgainstable)):
                    row[vindx.y(year, l)] = 1
                # Awful Hack! If year of asset sale, assume w(i,j)-D(i,j) is
                # negative so taxable from this is zero
                if S.cg_asset_taxed[year] <= 0:  # i.e., no sale
                    # last Acc is investment / stocks
                    j = len(S.accounttable) - 1
                    row[vindx.w(year, j)] = -1 * f
                    row[vindx.D(year, j)] = f
                A += [row]
                # b+=[0]
                b += [S.cg_asset_taxed[year]]
        #
        # Add constraints for (13b')
        #
        notes += [{"index": len(A), "note": "Constraints 13b':"}]
        if S.accmap['aftertax'] > 0:
            for year in range(S.numyr):
                f = self.cg_taxable_fraction(year)
                row = [0] * nvars
                # Awful Hack! If year of asset sale, assume w(i,j)-D(i,j) is
                # negative so taxable from this is zero
                if S.cg_asset_taxed[year] <= 0:  # i.e., no sale
                    # last Acc is investment / stocks
                    j = len(S.accounttable) - 1
                    row[vindx.w(year, j)] = f
                    row[vindx.D(year, j)] = -f
                for l in range(len(capgainstable)):
                    row[vindx.y(year, l)] = -1
                A += [row]
                # b+=[0]
                b += [-S.cg_asset_taxed[year]]
        #
        # Add constraints for (14')
        #
        notes += [{"index": len(A), "note": "Constraints 14':"}]
        if S.accmap['aftertax'] > 0:
            for year in range(S.numyr):
                adj_inf = S.i_rate**(S.preplanyears + year)
                for l in range(len(capgainstable) - 1):
                    row = [0] * nvars
                    row[vindx.y(year, l)] = 1
                    for k in range(len(taxtable) - 1):
                        if taxtable[k][0] >= capgainstable[l][0] and taxtable[k][0] < capgainstable[l + 1][0]:
                            row[vindx.x(year, k)] = 1
                    A += [row]
                    # mcg[i,l] inflation adjusted
                    b += [capgainstable[l][1] * adj_inf]
                    #print_constraint( row, capgainstable[l][1]*adj_inf)
        #
        # Add constraints for (15a')
        #
        notes += [{"index": len(A), "note": "Constraints 15a':"}]
        for year in range(S.numyr):
            for j in range(len(S.accounttable)):  # for all accounts
                # j = len(S.accounttable)-1 # nl the last account, the investment account
                row = [0] * nvars
                row[vindx.b(year + 1, j)] = 1  # b[i,j] supports an extra year
                row[vindx.b(year, j)] = -1 * S.accounttable[j]['rate']
                row[vindx.w(year, j)] = S.accounttable[j]['rate']
                row[vindx.D(year, j)] = -1 * S.accounttable[j]['rate']
                A += [row]
                # In the event of a sell of an asset for the year
                temp = [0]
                if S.accounttable[j]['acctype'] == 'aftertax':
                    temp = [S.asset_sale[year] *
                            S.accounttable[j]['rate']]  # TODO test
                b += temp
                #print('temp_a: ', temp, 'rate', S.accounttable[j]['rate'] , 'asset sell price: ', S.asset_sale[year]  )
        #
        # Add constraints for (15b')
        #
        notes += [{"index": len(A), "note": "Constraints 15b':"}]
        for year in range(S.numyr):
            for j in range(len(S.accounttable)):  # for all accounts
                # j = len(S.accounttable)-1 # nl the last account, the investment account
                row = [0] * nvars
                row[vindx.b(year, j)] = S.accounttable[j]['rate']
                row[vindx.w(year, j)] = -1 * S.accounttable[j]['rate']
                row[vindx.D(year, j)] = S.accounttable[j]['rate']
                row[vindx.b(year + 1, j)] = -1  # b[i,j] supports an extra year
                A += [row]
                temp = [0]
                if S.accounttable[j]['acctype'] == 'aftertax':
                    temp = [-1 * S.asset_sale[year] *
                            S.accounttable[j]['rate']]  # TODO test
                b += temp
                #print('temp_b: ', temp, 'rate', S.accounttable[j]['rate'] , 'asset sell price: ', S.asset_sale[year]  )
        #
        # Constraint for (16a')
        #   Set the begining b[1,j] balances
        #
        notes += [{"index": len(A), "note": "Constraints 16a':"}]
        for j in range(len(S.accounttable)):
            row = [0] * nvars
            row[vindx.b(0, j)] = 1
            A += [row]
            b += [S.accounttable[j]['bal']]
        #
        # Constraint for (16b')
        #   Set the begining b[1,j] balances
        #
        notes += [{"index": len(A), "note": "Constraints 16b':"}]
        for j in range(len(S.accounttable)):
            row = [0] * nvars
            row[vindx.b(0, j)] = -1
            A += [row]
            b += [-1 * S.accounttable[j]['bal']]
        #
        # Constrant for (17') is default for sycpy so no code is needed
        #
        notes += [{"index": len(A), "note": "Constraints 17':"}]
        if self.verbose:
            print("Num vars: ", len(c))
            print("Num contraints: ", len(b))
            print()

        return c, A, b, notes

    def cg_taxable_fraction(self, year):
        f = 1
        if self.S.accmap['aftertax'] > 0:
            for v in self.S.accounttable:
                if v['acctype'] == 'aftertax':
                    f = 1
                    if v['bal'] > 0:
                        f = 1 - (v['basis'] / (v['bal'] * v['rate']**year))
                    break  # should be the last entry anyway but...
        return f

    def print_model_matrix(self, c, A, b, notes, s, non_binding_only):
        note = ""
        notesIndex = 0
        nextModelIndex = len(A) + 1  # beyond the end of A
        if notes is not None:
            nextModelIndex = notes[notesIndex]["index"]
            note = notes[notesIndex]["note"]
            notesIndex += 1
        if nextModelIndex < 0:  # Object function index -1
            fromm = nextModelIndex
            nextModelIndex = notes[notesIndex].index
            to = nextModelIndex - 1
            print("\n##== [%d-%d]: %s ==##\n" % (fromm, to, note))
            note = notes[notesIndex].note
            notesIndex += 1
        if not non_binding_only:
            print("c: ")
            self.print_model_row(c)
            print()
            print("B? i: A_ub[i]: b[i]")
            for constraint in range(len(A)):
                if nextModelIndex == constraint:
                    fromm = nextModelIndex
                    nextModelIndex = notes[notesIndex]["index"]
                    to = nextModelIndex - 1
                    while to < fromm:
                        print("\n##== [%d-%d]: %s ==##\n" % (fromm, to, note))
                        note = notes[notesIndex]["note"]
                        notesIndex += 1
                        fromm = nextModelIndex
                        nextModelIndex = notes[notesIndex]["index"]
                        to = nextModelIndex - 1
                    print("\n##== [%d-%d]: %s ==##\n" % (fromm, to, note))
                    note = notes[notesIndex]["note"]
                    notesIndex += 1
                if s is None or s[constraint] > 0:
                    print("  ", end='')
                else:
                    print("B ", end='')
                print(constraint, ": ", sep='', end='')
                self.print_constraint(A[constraint], b[constraint])
        else:
            print(" i: A_ub[i]: b[i]")
            j = 0
            for constraint in range(len(A)):
                if nextModelIndex == constraint:
                    fromm = nextModelIndex
                    nextModelIndex = notes[notesIndex]["index"]
                    to = nextModelIndex - 1
                    while to < fromm:
                        print("\n##== [%d-%d]: %s ==##\n" % (fromm, to, note))
                        note = notes[notesIndex]["note"]
                        notesIndex += 1
                        fromm = nextModelIndex
                        nextModelIndex = notes[notesIndex]["index"]
                        to = nextModelIndex - 1
                    print("\n##== [%d-%d]: %s ==##\n" % (fromm, to, note))
                    note = notes[notesIndex]["note"]
                    notesIndex += 1
                if s[constraint] > 0:
                    j += 1
                    print(constraint, ": ", sep='', end='')
                    self.print_constraint(A[constraint], b[constraint])
            print("\n\n%d non-binding constrains printed\n" % j)
        print()

    def print_constraint(self, row, b):
        self.print_model_row(row, True)
        print("<= b[]: %6.2f" % b)

    def print_model_row(self, row, suppress_newline=False):

        S = self.S
        vindx = self.var_index
        taxtable = self.taxtable
        capgainstable = self.cgtaxtable
        #penalty = self.penalty
        #stded = self.stded
        #SS_taxable = self.ss_taxable

        for i in range(S.numyr):
            for k in range(len(taxtable)):
                if row[vindx.x(i, k)] != 0:
                    print("x[%d,%d]: %6.3f" %
                          (i, k, row[vindx.x(i, k)]), end=' ')
        if S.accmap['aftertax'] > 0:
            for i in range(S.numyr):
                for l in range(len(capgainstable)):
                    if row[vindx.y(i, l)] != 0:
                        print("y[%d,%d]: %6.3f " %
                              (i, l, row[vindx.y(i, l)]), end=' ')
        for i in range(S.numyr):
            for j in range(len(S.accounttable)):
                if row[vindx.w(i, j)] != 0:
                    print("w[%d,%d]: %6.3f " %
                          (i, j, row[vindx.w(i, j)]), end=' ')
        for i in range(S.numyr + 1):  # b[] has an extra year
            for j in range(len(S.accounttable)):
                if row[vindx.b(i, j)] != 0:
                    print("b[%d,%d]: %6.3f " %
                          (i, j, row[vindx.b(i, j)]), end=' ')
        for i in range(S.numyr):
            if row[vindx.s(i)] != 0:
                print("s[%d]: %6.3f " % (i, row[vindx.s(i)]), end=' ')
        # if S.accmap['aftertax'] > 0:
        for i in range(S.numyr):
            for j in range(len(S.accounttable)):
                if row[vindx.D(i, j)] != 0:
                    print("D[%d,%d]: %6.3f " %
                          (i, j, row[vindx.D(i, j)]), end=' ')
        if not suppress_newline:
            print()
