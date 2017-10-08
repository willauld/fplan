import sys
import os
import pickle
import unittest
import toml
import vector_var_index as v
import app_output
import taxinfo
import lp_constraint_model as lpclass
import tomldata
from ARetirementPlanner import solve

class TestIndexes(unittest.TestCase):
    """     Tests to ensure the set of functions index_?() are defined properly """

    def test_index_var_layout_with_aftertax(self):
        """     check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 1, 'aftertax': 1}
        
        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(z, msg='Variable index functions should count from 0 to #var-1')

    def test_index_var_layout_without_aftertax(self):
        """     check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 2, 'aftertax': 0}
        
        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(z)

class TestAppOutput(unittest.TestCase):
    def test_app_output_without_csv_file(self):
        ao = app_output.app_output(None)
        temp = sys.stdout
        sys.stdout = open('stdout.log', 'w')
        #sys.stderr = open('stderr.log', 'w')
        ao.output("1@2@3@4")
        sys.stdout.close()
        sys.stdout = temp
        inf = open('stdout.log', 'r')
        result = inf.read()
        #print("result: ", result)
        inf.close()
        self.assertEqual("1 2 3 4", result)
        try:
            os.remove('stdout.log')
        except OSError as e:  ## if failed, report it back to the user ##
            print ("Error: %s - %s." % (e.filename,e.strerror))

    def test_app_output_with_csv_file(self):
        fn = 'test_csv_file_for_unit_testing.csv'
        ao = app_output.app_output(fn)
        temp = sys.stdout
        sys.stdout = open('stdout.log', 'w')
        #sys.stderr = open('stderr.log', 'w')
        ao.output("1@2@3@4")
        sys.stdout.close()
        sys.stdout = temp
        inf = open('stdout.log', 'r')
        result = inf.read()
        #print("result: ", result)
        inf.close()
        self.assertEqual("1 2 3 4", result)
        del ao
        incsv = open(fn, 'r')
        result2 = incsv.read()
        #print("result2: ", result2)
        incsv.close()
        self.assertEqual("1,2,3,4", result2)
        try:
            os.remove('stdout.log')
            os.remove(fn)
        except OSError as e:  ## if failed, report it back to the user ##
            print ("Error: %s - %s." % (e.filename,e.strerror))

class TestLpConstraintModel(unittest.TestCase):
    # TODO define some good test for model construction and printing
    #def __init__(self, ?unit_test?):
    #    self.toml_file = None

    def write_working_toml_file(self):
        tomls = """
returns = 6
inflation = 2.5
[aftertax]
bal = 700000
basis = 400000
contrib = 10
period = "56-65"
[iam.spouse]
primary = false
age = 54
retire = 60
through = 75
[iam.will]
primary = true
age = 56
retire = 58
through = 72
[SocialSecurity.will]
amount = 31000
FRA = 67
age = "68-"
[SocialSecurity.spouse]
amount = 21000
FRA = 67
age = "70-"
[income.mytaxfree]
amount = 3000
age = "56-"
inflation = false
tax = false
[income.rental_1]
amount = 36000
age = "67-"
inflation = true
tax = true
[income.rental_2]
amount = 2400
age = "67-"
inflation = true
tax = true
[IRA.will]
bal = 2000000
contrib = 100
inflation = true
period = "56-65"
[IRA.spouse]
bal = 200000
[roth.spouse]
bal = 100000
contrib = 0
        """
        self.toml_file = None
        self.toml_file_name = 'self_temp_toml.toml'
        self.bin_constraint_name = 'constrain_model_test_file.bcm' # bcm = binary constraint model 
        #with open('Anew.toml') as f:
        #    parsed_toml = toml.loads(f.read())
        #new_toml_str = toml.dumps(parsed_toml)

        #print("tomls: %s" % tomls)
        self.toml_file = open(self.toml_file_name, 'w')
        self.toml_file.write(tomls)
        #self.toml_file.flush()
        self.toml_file.close()

    def __del__(self):
        # TODO delete the toml file!!!!
        try:
            os.remove(self.toml_file_name)
        except OSError as e:  ## if failed, report it back to the user ##
            print ("Error: %s - %s." % (e.filename,e.strerror))

    def lp_constraint_model_load_default_toml(self):
        self.write_working_toml_file()
        S = tomldata.Data()
        S.load_file(self.toml_file_name) 
        return S

    def lp_constraint_model_build_model(self, S):
        years = S.numyr
        taxbins = len(taxinfo.taxtable)
        cgbins = len(taxinfo.capgainstable)
        accounts = len(S.accounttable) 
        verbose = False
        vindx = v.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
        lp = lpclass.lp_constraint_model(S, vindx, taxinfo.taxtable, taxinfo.capgainstable, taxinfo.penalty, taxinfo.stded, taxinfo.SS_taxable, verbose)
        c, A, b = lp.build_model()
        return vindx, lp, c, A, b

    def test_lp_constraint_model_contrib_IRA1(self):
        S = self.lp_constraint_model_load_default_toml()
        # TODO: add any local changes to the initial data
        # default toml has IRA.will contrib 100 with inflation from 56-65, No need to modify
        vindx, lp, c, A, b = self.lp_constraint_model_build_model(S)
        # TODO: Test created model or solve...
        verbose = False
        res = solve(c, A, b, verbose)
        self.assertGreaterEqual (res.x[vindx.D(0,0)],100) # TODO change index to find correct values for owner and age
        # TODO, now check for the rest of the values between ages 56-65 (maybe shorten this time period)

    def test_lp_constraint_model_build_against_know_model(self):
        S = self.lp_constraint_model_load_default_toml()
        # TODO: add any local changes to the initial data
        vindx, lp, c, A, b = self.lp_constraint_model_build_model(S)
        # TODO: Test created model or solve...

        #with open(self.bin_constraint_name, 'wb') as fil: # USE TO UPDATE THE BINARY 'GOOD' model
        #    pickle.dump([c, A, b], fil)

        with open(self.bin_constraint_name, 'rb') as fil:
            [nc, nA, nb] = pickle.load(fil)
        
        #Do a deep compare:
        self.assertEqual(pickle.dumps([c, A, b]), pickle.dumps([nc, nA, nb])) 

        self.model_matrix_name = 'known_good_model_matrix.pickle'
        temp = sys.stdout
        sys.stdout = open('stdout.log', 'w')
        #sys.stderr = open('stderr.log', 'w')

        lp.print_model_matrix(c, A, b, None, False)

        sys.stdout.close()
        sys.stdout = temp
        inf = open('stdout.log', 'r')
        result = inf.read()
        #print("result: ", result)
        inf.close()

        #with open(self.model_matrix_name, 'wb') as fil1: # USE TO UPDATE THE BINARY 'GOOD' model matrix
        #    pickle.dump(result, fil1)

        with open(self.model_matrix_name, 'rb') as fil2:
            known_good = pickle.load(fil2)

        self.assertEqual(pickle.dumps(result), pickle.dumps(known_good)) 

        try:
            os.remove('stdout.log')
        except OSError as e:  ## if failed, report it back to the user ##
            print ("Error: %s - %s." % (e.filename,e.strerror))

class TestTomlInput(unittest.TestCase):
    """ Tests to ensure we are getting the correct and needed input from toml configuration file """

    def test_toml_input_(self):
        pass


if __name__ == '__main__':
    unittest.main()
