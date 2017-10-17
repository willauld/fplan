
import json # strickly to make a deep copy # threadsafe deepcopy
import toml
#import argparse
#import scipy.optimize
import re
#import taxinfo ### TODO replace the following line with this one and edits to this file
from taxinfo import accountspecs, taxtable, capgainstable, penalty, stded, SS_taxable, contribspecs, RMD
#import vector_var_index as vvar
#import app_output as app_out
#import lp_constraint_model as lp

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
        ## This routine looks a the categories and there labeled components (keys) to 
        ## ensure a uniform structure for later processing
        ##
        rec = dict.get(type,{}) 
        #print('check_record(%s): to check ' % type, rec)
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
        #print('check_record(%s): checked ' % type, dict.get(type,{}))

    def maxContribution(self, year, retireekey):
        ### not currently handling 401K max contributions TODO
        max = 0
        for v in self.retiree:
            if retireekey is None or v['mykey'] == retireekey: # Sum all retiree
                max += contribspecs['TDRA']
                age = v['ageAtStart'] + year
                if age >= contribspecs['CatchupAge']:
                    max += contribspecs['TDRACatchup']
        max *= self.i_rate ** year # adjust for inflation
        #print('maxContribution: %6.0f' % max, retireekey)
        return max

    def match_retiree(self, retireekey):
        for v in self.retiree:
            #print("    retiree: ", v)
            if v['mykey'] == retireekey:
                return v
        return None
        
    def rmd_needed(self,year,retireekey):
        rmd = 0
        v = self.match_retiree(retireekey)
        if v is None:
            #print("RMD_NEEDED() year: %d, rmd: %6.3f, Not Valid Retiree, retiree: %s" % (year, rmd, retireekey))
            return rmd
        age = v['ageAtStart']+year
        if age >= 70: # IRA retirement: minimum distribution starting age 70.5 
            rmd = RMD[age - 70]
        #print("RMD_NEEDED() year: %d, rmd: %6.3f, age: %d, retiree: %s" % (year, rmd, age, retireekey))
        return rmd

    def account_owner_age(self,year,account):
        retireekey = account['mykey']
        v = self.match_retiree(retireekey)
        age = v['ageAtStart']+year
        return age

    def apply_early_penalty(self,year,retireekey):
        response = False
        v = self.match_retiree(retireekey)
        if v is None:
            return response
        age = v['ageAtStart']+year
        if age < 60: # IRA retirement account require penalty if withdrawn before age 59.5
            response = True
        return response

    def load_toml_file(self, file):
        with open(file) as conffile:
            self.toml_dict = toml.loads(conffile.read())
            conffile.close()
        #print("\n\nun tarnished dict: ", self.toml_dict)
        #for f in self.toml_dict:
        #    print("\ndict[%s] = " % (f),self.toml_dict[f])
        #print()

    def get_account_info(self, d, type):
            index = 0
            lis_return = []
            for k,v in d.get( type , {}).items():
                entry = {}
                entry['acctype'] = type
                entry['index'] = index
                entry['estateTax'] = accountspecs[type]['tax']
                entry['origbal'] = v['bal']
                entry['bal'] = v['bal']
                entry['mykey'] = k
                r = self.match_retiree(k)
                if r is None:
                    if type == 'IRA' or type == 'roth':
                        print("Error: Account must match a retiree\n\t[%s.%s] should match [iam.%s] but there is no [iam.%s]\n"%(type,k,k,k))
                        exit(1)
                    ageAtStart = self.match_retiree(self.primary)['ageAtStart']
                    currentAge = self.match_retiree(self.primary)['age']
                else:
                    ageAtStart = r['ageAtStart']
                    currentAge = r['age']
                if 'rate' not in v:
                    entry['rate'] = self.r_rate 
                    v['rate'] = self.r_rate 
                else:
                    rate = 1 + v['rate'] / 100  # invest rate: 6 -> 1.06
                    entry['rate'] = rate
                    v['rate'] = rate
                precontribs = 0
                precontibsPlusReturns = 0
                tillRetirement = ageAtStart - currentAge
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
                                preyear = age - currentAge
                                if year < 0:
                                    # capture all contributions before start of retirement
                                    b = entry['contrib'] 
                                    if entry['inflation']:
                                        b = entry['contrib'] * self.i_rate ** preyear
                                    precontribs += b
                                    precontibsPlusReturns += b
                                    precontibsPlusReturns *= entry['rate']
                                    continue
                                elif year >= self.numyr:
                                    break
                                else:
                                    bucket[year] = entry['contrib'] 
                                    if entry['inflation']:
                                        bucket[year] = entry['contrib'] * self.i_rate ** (preyear+year)
                                    #print("age %d, year %d, bucket: %6.0f += amount %6.0f" %(age, year, bucket[year], adj_amount))
                if type == 'aftertax':
                    if 'basis' not in v:
                        entry['basis'] = 0
                        v['basis'] = 0
                    else:
                        entry['origbasis'] = v['basis']
                        entry['basis'] = v['basis'] + precontribs 
                entry['bal'] = v['bal'] * v['rate'] ** tillRetirement + precontibsPlusReturns
                lis_return.append(entry)
                #print('entry: ', entry)
                index += 1
            return lis_return

    def process_toml_info(self):

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
        d = json.loads(json.dumps(self.toml_dict)) #thread safe deep copy
        #"""
        #print("\n\nun tarnished dict: ", d)
        #for f in d:
        #    print("\ndict[%s] = " % (f),d[f])
        #print()
        #"""
        
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
        self.accounttable += self.get_account_info(d, 'IRA') # returns entry for each account
        self.accounttable += self.get_account_info(d, 'roth') 
        self.accounttable += self.get_account_info(d, 'aftertax') 
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
        do_details("desired", WANT, None) # TODO move this from a vector to a single amount for starting year
        do_details("max", MAX, None) # TODO move this from a vector to a single amount for starting year
        do_SS_details(SS)

        self.income = INC
        self.expenses = EXP 
        self.taxed = TAX
        self.desired = WANT
        self.max = MAX
        self.SS = SS 
