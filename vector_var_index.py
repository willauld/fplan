

def my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, varindex):
    """ varindex.?() functions are laid out to index a vector of variables
        laid out in the order x(i,k), y(i,l), w(i,j), b(i,j), s(i), D(i), ns() """
    pass_ok = True
    ky = 0
    #row = [0] * nvars
    for i in range(years):
        for k in range(taxbins):
            if varindex.x(i, k) != ky:
                pass_ok = False
                print("varindex.x(%d,%d) is %d not %d as it should be" % (i,k,varindex.x(i,k), ky))
            ky += 1
    if accmap['aftertax'] > 0:
        for i in range(years):
            for l in range(cgbins):
                if varindex.y(i, l) != ky:
                    pass_ok = False
                    print("varindex.y(%d,%d) is %d not %d as it should be" % (i,l,varindex.y(i,l), ky))
                ky += 1
    for i in range(years):
        for j in range(accounts):
            if varindex.w(i, j) != ky:
                pass_ok = False
                print("varindex.w(%d,%d) is %d not %d as it should be" % (i, j, varindex.w(i,j), ky))
            ky += 1
    for i in range(years+1): # b[] has an extra year
        for j in range(accounts):
            if varindex.b(i, j) != ky:
                pass_ok = False
                print("varindex.b(%d,%d) is %d not %d as it should be" % (i, j, varindex.b(i,j), ky))
            ky += 1
    for i in range(years):
        if varindex.s(i) != ky:
            pass_ok = False
            print("varindex.s(%d) is %d not %d as it should be" % (i, varindex.s(i), ky))
        ky += 1
    if accmap['aftertax'] > 0:
        for i in range(years):
            for j in range(accounts):
                if varindex.D(i,j) != ky:
                    pass_ok = False
                    print("varindex.D(%d,%d) is %d not %d as it should be" % (i, j, varindex.D(i,j), ky))
                ky += 1
    return pass_ok

class vector_var_index:
    """ inplements the vector var index functions """

    def __init__(self, iyears, itaxbins, icgbins, iaccounts, iaccmap):

        self.years = iyears
        self.taxbins = itaxbins
        self.cgbins = icgbins
        self.accounts = iaccounts
        self.accmap = iaccmap

        self.xcount = self.years*self.taxbins
        self.ycount = 0
        if self.accmap['aftertax'] > 0: # no cgbins if no aftertax account
            self.ycount = self.years*self.cgbins
        self.wcount = self.years*self.accounts
        self.bcount = (self.years+1)*self.accounts # final balances in years+1
        self.scount = self.years
        self.Dcount = self.years*self.accounts
        self.vsize = self.xcount + self.ycount + self.wcount + self.bcount + self.scount + self.Dcount

        #xstart = 0
        self.ystart = self.xcount
        self.wstart = self.ystart + self.ycount
        self.bstart = self.wstart + self.wcount
        self.sstart = self.bstart + self.bcount
        self.Dstart = self.sstart + self.scount

    def x(self, i, k):
        assert i>=0 and i < self.years
        assert k>=0 and k < self.taxbins
        return i*self.taxbins+k

    def y(self, i,l):
        assert self.accmap['aftertax'] > 0
        assert i>=0 and i < self.years
        assert l>=0 and l < self.cgbins
        return self.ystart + i*self.cgbins+l

    def w(self, i,j):
        assert i>=0 and i < self.years
        assert j>=0 and j < self.accounts
        return self.wstart + i*self.accounts+j

    def b(self, i,j):
        assert i>=0 and i < self.years+1 # b has an extra year on the end 
        assert j>=0 and j < self.accounts
        return self.bstart + i*self.accounts+j

    def s(self, i):
        assert i>=0 and i < self.years
        return self.sstart + i

    def D(self, i,j):
        #assert S.accmap['aftertax'] > 0
        assert j>=0 and j < self.accounts
        assert i>=0 and i < self.years
        return self.Dstart + i*self.accounts + j
