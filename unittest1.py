import sys
import os
import pickle
import unittest
import json
import argparse
import toml
import scipy.optimize
import vector_var_index as v
import app_output
import taxinfo as tif
import lp_constraint_model as lpclass
import tomldata
#import cfg_master  #has the optparse option-handling code

orig_tomls = """
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
[income.stopgap]
amount = 300
age = "56-"
inflation = false
tax = true
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

class working_toml_file:
    def __init__(self, filename, skip_file_write=None, skip_file_delete=None):
        self.toml_file_name = filename
        #self.toml_file_name = 'self_temp_toml.toml'
        self.tomls = orig_tomls
        if skip_file_write is None or skip_file_write == False:
            self.write_working_toml_file(self.tomls)
        self.skip_file_delete = False
        if skip_file_delete is not None and skip_file_delete is True:
            self.skip_file_delete = True

    def toml_dict(self, dict=None):
        if dict is None:
            toml_dict = toml.loads(self.tomls)
            return toml_dict
        self.tomls = toml.dumps(dict)

    def write_working_toml_file(self, use_tomls):
        self.toml_file = open(self.toml_file_name, 'w')
        self.toml_file.write(use_tomls)
        # self.toml_file.flush()
        self.toml_file.close()

    def __del__(self):
        if self.skip_file_delete is False:
            try:
                os.remove(self.toml_file_name)
            except OSError as e:  # if failed, report it back to the user ##
                print("WGA Error: %s - %s." % (e.filename, e.strerror))


class TestIndexes(unittest.TestCase):
    """.    Tests to ensure the set of functions index_?() are defined properly """

    def test_index_var_layout_with_aftertax(self):
        """.    check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 1, 'aftertax': 1}

        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(
            years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(
            z, msg='Variable index functions should count from 0 to #var-1')

    def test_index_var_layout_without_aftertax(self):
        """.    check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 2, 'aftertax': 0}

        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(
            years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(z)


class TestAppOutput(unittest.TestCase):
    def test_app_output_without_csv_file(self):
        ao = app_output.app_output(None)
        temp = sys.stdout
        sys.stdout = open('stdout.log', 'w')
        #sys.stderr = open('stderr.log', 'w')
        ao.output("1&@2&@3&@4")
        sys.stdout.close()
        sys.stdout = temp
        inf = open('stdout.log', 'r')
        result = inf.read()
        #print("result: ", result)
        inf.close()
        self.assertEqual("1 2 3 4", result, msg='result is: {}'.format(result))
        try:
            os.remove('stdout.log')
        except OSError as e:  # if failed, report it back to the user ##
            print("Error: %s - %s." % (e.filename, e.strerror))

    def test_app_output_with_csv_file(self):
        fn = 'test_csv_file_for_unit_testing.csv'
        ao = app_output.app_output(fn)
        temp = sys.stdout
        sys.stdout = open('stdout.log', 'w')
        #sys.stderr = open('stderr.log', 'w')
        ao.output("1&@2&@3&@4")
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
        except OSError as e:  # if failed, report it back to the user ##
            print("Error: %s - %s." % (e.filename, e.strerror))


class TestLpConstraintModel(unittest.TestCase):
    # TODO define some good test for model construction and printing
    def __init__(self, other):
        # bcm = binary constraint model
        self.bin_constraint_name = 'constrain_model_test_file.bcm'
        super().__init__(other)

    def lp_constraint_model_load_default_toml(self):
        toml_file_name = 'self_temp_toml.toml'
        tf = working_toml_file(toml_file_name)
        self.taxinfo = tif.taxinfo()
        S = tomldata.Data(self.taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        return S

    def lp_constraint_model_build_model(self, S):
        years = S.numyr
        taxbins = len(self.taxinfo.taxtable)
        cgbins = len(self.taxinfo.capgainstable)
        accounts = len(S.accounttable)
        verbose = False
        vindx = v.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
        lp = lpclass.lp_constraint_model(S, vindx, self.taxinfo.taxtable, self.taxinfo.capgainstable,
                                         self.taxinfo.penalty, self.taxinfo.stded, self.taxinfo.SS_taxable, verbose)
        c, A, b = lp.build_model()
        return vindx, lp, c, A, b

    def test_lp_constraint_model_contrib_IRA1(self):
        S = self.lp_constraint_model_load_default_toml()
        # TODO: add any local changes to the initial data
        # default toml has IRA.will contrib 100 with inflation from 56-65, No need to modify
        vindx, lp, c, A, b = self.lp_constraint_model_build_model(S)
        # TODO: Test created model or solve...
        verbose = False
        #res = solve(c, A, b, verbose)
        res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                     options={"disp": verbose,
                                              #"bland": True,
                                              "tol": 1.0e-7,
                                              "maxiter": 3000})
        self.assertTrue(res.success, msg='res.success indicates solver failed')
        # TODO change the index calculation to load data not my hand chosen numbers
        for i in range(65 - max(56, 57)):
            # check all the values between ages 56-65
            atleast = 100 * S.i_rate**i
            # TODO change account index to find correct values for owner account
            self.assertGreaterEqual(
                res.x[vindx.D(i, 0)], atleast,
                msg='Contribution should be at least {} but is {}'.format(atleast, res.x[vindx.D(i, 0)]))
        onePassedYear = 65 - max(56, 57) + 1
        # TODO change account index to find correct values for owner account
        self.assertLess(
            res.x[vindx.D(onePassedYear, 0)], atleast,
            msg='Contribution should likely be less than previous year contribution {} and is {}'.format(atleast, res.x[vindx.D(onePassedYear, 0)]))

    def test_lp_constraint_model_build_against_know_model(self):
        S = self.lp_constraint_model_load_default_toml()
        # TODO: add any local changes to the initial data
        vindx, lp, c, A, b = self.lp_constraint_model_build_model(S)
        # TODO: Test created model or solve...

        #with open(self.bin_constraint_name, 'wb') as fil:  # USE TO UPDATE THE BINARY 'GOOD' model
        #   pickle.dump([c, A, b], fil)

        with open(self.bin_constraint_name, 'rb') as fil:
            [nc, nA, nb] = pickle.load(fil)

        # Do a deep compare:
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

        # USE TO UPDATE THE BINARY 'GOOD' model matrix
        #with open(self.model_matrix_name, 'wb') as fil1:
        #    pickle.dump(result, fil1)

        with open(self.model_matrix_name, 'rb') as fil2:
            known_good = pickle.load(fil2)

        self.assertEqual(pickle.dumps(result), pickle.dumps(known_good))

        try:
            os.remove('stdout.log')
        except OSError as e:  # if failed, report it back to the user ##
            print("Error: %s - %s." % (e.filename, e.strerror))


class TestInputThroughSolver(unittest.TestCase):
    def __init__(self, other):
        #self.taxinfo = tif.taxinfo()
        super().__init__(other)

    def test_input_through_solver_joint_first_year_spinding(self):
        toml_file_name = 't.toml'
        skipfilewrite = True
        tf = working_toml_file(toml_file_name, skipfilewrite)
        dict =tf.toml_dict()
        dict['retirement_type'] = 'joint'
        tf.toml_dict(dict) # update tf.tomls
        tf.write_working_toml_file(tf.tomls)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()

        years = S.numyr
        taxbins = len(taxinfo.taxtable)
        cgbins = len(taxinfo.capgainstable)
        accounts = len(S.accounttable)
        verbose = False
        vindx = v.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
        lp = lpclass.lp_constraint_model(S, vindx, taxinfo.taxtable,
                                        taxinfo.capgainstable,
                                        taxinfo.penalty, 
                                        taxinfo.stded, 
                                        taxinfo.SS_taxable, verbose)
        c, A, b = lp.build_model()

        res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                     options={"disp": verbose,
                                              #"bland": True,
                                              "tol": 1.0e-7,
                                              "maxiter": 3000})
        self.assertTrue(res.success, msg='res.success indicates solver failed')
        # If we get this far test the output
        year = 0
        verifiedSolverResult = 224992.9610
        latestSolverResult = res.x[vindx.s(year)]
        self.assertEqual(round(latestSolverResult,3), round(verifiedSolverResult,3), msg='Verified solver result is ${:0_.3f} but here we got ${:0_.3f}'.format(verifiedSolverResult, latestSolverResult))

    def test_input_through_solver_mseparate_first_year_spinding(self):
        toml_file_name = 't.toml'
        skipfilewrite = True
        tf = working_toml_file(toml_file_name, skipfilewrite)
        dict =tf.toml_dict()
        dict['retirement_type'] = 'mseparate'
        tf.toml_dict(dict) # update tf.tomls
        tf.write_working_toml_file(tf.tomls)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()

        years = S.numyr
        taxbins = len(taxinfo.taxtable)
        cgbins = len(taxinfo.capgainstable)
        accounts = len(S.accounttable)
        verbose = False
        vindx = v.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
        lp = lpclass.lp_constraint_model(S, vindx, taxinfo.taxtable,
                                        taxinfo.capgainstable,
                                        taxinfo.penalty, 
                                        taxinfo.stded, 
                                        taxinfo.SS_taxable, verbose)
        c, A, b = lp.build_model()

        res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                     options={"disp": verbose,
                                              #"bland": True,
                                              "tol": 1.0e-7,
                                              "maxiter": 3000})
        self.assertTrue(res.success, msg='res.success indicates solver failed')
        # If we get this far test the output
        year = 0
        verifiedSolverResult = 211716.375
        self.assertEqual(round(res.x[vindx.s(year)],3), round(verifiedSolverResult,3), msg='Verified solver result is ${:0_.3f} but here we got ${:0_.3f}'.format(verifiedSolverResult, res.x[vindx.s(year)]))

    def test_input_through_solver_single_first_year_spinding(self):
        toml_file_name = 't.toml'
        skipfilewrite = True
        tf = working_toml_file(toml_file_name, skipfilewrite)
        dict =tf.toml_dict()
        dict['retirement_type'] = 'single'
        tf.toml_dict(dict) # update tf.tomls
        tf.write_working_toml_file(tf.tomls)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()

        years = S.numyr
        taxbins = len(taxinfo.taxtable)
        cgbins = len(taxinfo.capgainstable)
        accounts = len(S.accounttable)
        verbose = False
        vindx = v.vector_var_index(years, taxbins, cgbins, accounts, S.accmap)
        lp = lpclass.lp_constraint_model(S, vindx, taxinfo.taxtable,
                                        taxinfo.capgainstable,
                                        taxinfo.penalty, 
                                        taxinfo.stded, 
                                        taxinfo.SS_taxable, verbose)
        c, A, b = lp.build_model()

        res = scipy.optimize.linprog(c, A_ub=A, b_ub=b,
                                     options={"disp": verbose,
                                              #"bland": True,
                                              "tol": 1.0e-7,
                                              "maxiter": 3000})
        self.assertTrue(res.success, msg='res.success indicates solver failed')
        # If we get this far test the output
        year = 0
        verifiedSolverResult = 214422.3170
        self.assertEqual(round(res.x[vindx.s(year)],3), round(verifiedSolverResult,3), msg='Verified solver result is ${:0_.3f} but here we got ${:0_.3f}'.format(verifiedSolverResult, res.x[vindx.s(year)]))


class TestTomlInput(unittest.TestCase):
    """ Tests to ensure we are getting the correct and needed input from toml configuration file """

    def test_toml_agelist(self):
        for age in tomldata.agelist('55-67'):
            self.assertGreaterEqual(age, 55, msg='age must be at least 55')
            self.assertLessEqual(age, 67, msg='age must not exceed 67')
        for age in tomldata.agelist('25'):
            self.assertEqual(age, 25, msg='age must be 25')

    def test_toml_input_load_load_toml_file_to_match_crator_string(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        s1 = tf.tomls.lstrip().rstrip()
        s2 = toml.dumps(S.toml_dict).rstrip()
        self.assertEqual(s1, s2)

    def test_toml_input_load_missing_toml_file_will_fail(self):
        toml_file_name = 't.toml'
        # Since the next two lines stops the toml file from 
        # being written in the background it must be explicitly
        # written or will not exist as in this test.
        skipfilewrite = True
        tf = working_toml_file(toml_file_name, skipfilewrite)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        expect_exception = FileNotFoundError(2,'No such file or directory: \'t.toml\'')
        with self.assertRaises(OSError) as cm:
            S.load_toml_file(toml_file_name) #This should fail
        self.assertEqual(str(cm.exception), str(expect_exception))

    def test_toml_input_load_update_dictionary(self):
        toml_file_name = 't.toml'
        skipfilewrite = True
        tf = working_toml_file(toml_file_name, skipfilewrite)
        dict =tf.toml_dict()
        dict['retirement_type'] = 'single'
        tf.toml_dict(dict) # update tf.tomls
        tf.write_working_toml_file(tf.tomls)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        self.assertEqual(S.retirement_type, 'single', msg='Explicitly setting retirement_type to single so it should match')

    def test_toml_input_process_toml_info(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # TODO What to do to test this???

    # Assumes process_toml_info() has run
    def test_toml_input_match_retiree(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        retiree1 = 'will'
        retiree2 = 'spouse'
        retireeNot = 'joe'
        v = S.match_retiree(retiree1)
        self.assertEqual(v['mykey'], retiree1)
        v = S.match_retiree(retiree2)
        self.assertEqual(v['mykey'], retiree2)
        v = S.match_retiree(retireeNot)
        self.assertEqual(v, None)

    # Assumes process_toml_info() has run
    def test_toml_input_load_rmd_needed(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # toml has age 56, retire 58, through 72 primary so ageAtStart 58 (retire age)
        retiree1 = 'will'
        retiree2 = 'spouse'  # toml has age 54, retire 60, through 75 secondary so ageAtStart 56
        retireeNot = 'joe'
        rmd = S.rmd_needed(69 - 58, retiree1)
        self.assertEqual(
            rmd, 0, msg='At age 69 there should be no RMD (i.e., zero)')
        rmd = S.rmd_needed(70 - 58, retiree1)
        self.assertGreater(
            rmd, 0, msg='At age 70, RMD should be the IRS life expectancy')
        rmd = S.rmd_needed(69 - 56, retiree2)
        self.assertEqual(
            rmd, 0, msg='At age 69 there should be no RMD (i.e., zero)')
        rmd = S.rmd_needed(70 - 56, retiree2)
        self.assertGreater(
            rmd, 0, msg='At age 70, RMD should be the IRS life expectancy')
        rmd = S.rmd_needed(69 - 56, retireeNot)
        self.assertEqual(
            rmd, 0, msg='Non-valid Retiree should alway return rmd 0')

    # Assumes process_toml_info() has run
    def test_toml_input_apply_early_penalty(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # toml has age 56, retire 58, through 72 primary so ageAtStart 58 (retire age)
        retiree1 = 'will'
        retiree2 = 'spouse'  # toml has age 54, retire 60, through 75 secondary so ageAtStart 56
        retireeNot = 'joe'
        p = S.apply_early_penalty(59 - 58, retiree1)
        self.assertTrue(
            p, msg='At age 59 an early penalty is require, unless...')
        p = S.apply_early_penalty(60 - 58, retiree1)
        self.assertFalse(p, msg='At age 60 no early penalty is require')
        p = S.apply_early_penalty(59 - 56, retiree2)
        self.assertTrue(
            p, msg='At age 59 an early penalty is require, unless...')
        p = S.apply_early_penalty(60 - 56, retiree2)
        self.assertFalse(p, msg='At age 60 no early penalty is require')
        p = S.apply_early_penalty(59 - 56, retireeNot)
        self.assertFalse(p, msg='A non-existant retiree should return false')

    # Assumes process_toml_info() has run
    def test_toml_input_account_owner_age(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        for account in S.accounttable:
            if account['acctype'] != 'aftertax':
                year = 59 - 58  # age - start of plan age for will
                if account['mykey'] != 'will':
                    year = 59 - 56  # age - start of plan age for spouse
                a = S.account_owner_age(year, account)
                self.assertEqual(
                    a, 59, msg='At age 59 account_owner_age() should be 59')

    # Assumes process_toml_info() has run
    def test_toml_input_maxcontribution(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # toml has age 56, retire 58, through 72 primary so ageAtStart 58 (retire age)
        retiree1 = 'will'
        retiree2 = 'spouse'  # toml has age 54, retire 60, through 75 secondary so ageAtStart 56
        retireeNot = 'joe'
        retireeNone = None
        year = 1
        m = S.maxContribution(year, retiree1)
        self.assertEqual(m, (taxinfo.contribspecs['TDRA'] + taxinfo.contribspecs['TDRACatchup'])
                         * S.i_rate**year, msg='TDRA+RothRA contribution plus catchup')
        m = S.maxContribution(year, retireeNot)
        self.assertEqual(m, 0, msg='zero if non-existant retiree')
        m = S.maxContribution(year, retireeNone)
        self.assertEqual(m, 2 * (taxinfo.contribspecs['TDRA'] + taxinfo.contribspecs['TDRACatchup'])
                         * S.i_rate**year, msg='TDRA+RothRA contribution plus catchup for both Retirees')

    def test_toml_input_check_record(self):
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        orig = {'aftertax': {'bal': 700000, 'basis': 400000,
                             'contrib': 10, 'period': '56-65'}}
        to = {'aftertax': {'nokey': {'bal': 700000,
                                     'basis': 400000, 'contrib': 10, 'period': '56-65'}}}
        d = json.loads(json.dumps(orig))  # thread safe deep copy
        S.check_record(d, 'aftertax', ('bal', 'rate', 'contrib',
                                       'inflation', 'period', 'basis'))
        # Do a deep compare:
        self.assertEqual(pickle.dumps(to), pickle.dumps(
            d), msg='dictionary should be transformed')
        orig = {}
        to = {}
        d = json.loads(json.dumps(orig))  # thread safe deep copy
        S.check_record(d, 'aftertax', ('bal', 'rate', 'contrib',
                                       'inflation', 'period', 'basis'))
        # Do a deep compare:
        self.assertEqual(pickle.dumps(to), pickle.dumps(
            d), msg='{} dictionary should remain {}')

    # Assumes process_toml_info() has run
    def test_toml_input_account_info(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        #S = tomldata.Data()
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # tmol Accounts
        # IRA.will    bal=2,000,000 contrib=100 inflation=true period=56-65 {inflation applies to contrib}
        # IRA.spouse  bal=200,000   contrib=0   inflation=false period=
        # Roth.spouse bal=100,000   contrib=0   inflation=false period=
        # aftertax    bal=700,000   contrib=10  inflation=false period=56-65
        # Plan period 58-73, age will 56 age spouse 54
        for acc in S.accounttable:
            origbal = acc['origbal']
            bal = acc['bal']
            mykey = acc['mykey']
            acctype = acc['acctype']
            if (acctype == 'IRA' or acctype == 'roth') and mykey == 'spouse':
                self.assertEqual(bal, origbal * S.r_rate**(58 - 56),
                                 msg='Rate of return till plan start, no contributions')
            elif mykey == 'will' or mykey == 'nokey':
                calcb = origbal * S.r_rate**(58 - 56)
                contrib = acc['contrib']
                p = contrib * (S.r_rate**(58 - 56) - 1) * \
                    (1 + (1 / (S.r_rate - 1)))
                pwicontrib = (contrib * (1 - (S.r_rate * S.i_rate) **
                                         (60 - 58)) / (1 - S.r_rate * S.i_rate)) * (S.r_rate)
                age60contrib = acc['contributions'][60 - 58]
                if acc['inflation'] == False:
                    self.assertEqual(
                        bal, calcb + p, msg='Rate of return and contributions till plan start')
                    self.assertEqual(
                        contrib, age60contrib, msg='No inflation so all contrib values should match')
                else:
                    self.assertEqual(round(bal, 0), round(
                        calcb + pwicontrib, 0), msg='Rate of return and inflating contributions till plan start')
                    self.assertEqual(contrib * S.i_rate**(60 - 56), age60contrib,
                                     msg='Inflation so contrib values should increase each year with inflation')

    # Assumes process_toml_info() has run
    def test_toml_input_retiree_info(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # TODO TEST ME

    def test_toml_input_start_amount(self):
        S = tomldata.Data(None)
        amount = 12000
        fra = 67
        start = 62
        a = S.startamount(amount, fra, start)
        b = amount / (1.067**(fra - start))
        self.assertEqual(a, b)
        start = 70
        a = S.startamount(amount, fra, start)
        b = amount * (1.08**(start - fra))
        self.assertEqual(a, b)
        start = fra
        a = S.startamount(amount, fra, start)
        self.assertEqual(a, amount)
        start = 61  # test 61 and should fail too young
        a = S.startamount(amount, fra, start)
        # will not go to 61, 62 is lower bound
        b = amount / (1.067**(fra - 62))
        self.assertEqual(a, b)

    # Assumes process_toml_info() has run
    def test_toml_input_do_ss_details(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        # [iam.will] primary = true, age = 56, retire = 58, through = 72
        # [SocialSecurity.will] amount = 31000 FRA = 67 age = "68-"
        # [iam.spouse] primary = false, age = 54, retire = 60, through = 75
        # [SocialSecurity.spouse] amount = 21000 FRA = 67 age = "70-"
        # => let's check the SS when spouse is 70 and will is 72 ->SS[72-58]
        willcontrib = (31000 * (1.08**(68 - 67))) * 1.025**(72 - 56)
        spousecontrib = (21000 * (1.08**(70 - 67))) * 1.025**(70 - 54)
        expect = willcontrib + spousecontrib
        self.assertEqual(S.SS[72 - 58], expect)

    # Assumes process_toml_info() has run
    def test_toml_input_do_details(self):
        toml_file_name = 't.toml'
        tf = working_toml_file(toml_file_name)
        taxinfo = tif.taxinfo()
        S = tomldata.Data(taxinfo)
        S.load_toml_file(toml_file_name)
        S.process_toml_info()
        #[income.mytaxfree] amount = 3000 age = "56-" inflation = false tax = false
        #[income.rental_1] amount = 36000 age = "67-" inflation = true tax = true
        #[income.rental_2] amount = 2400 age = "67-" inflation = true tax = true
        # => let's check the INC when will is 65->INC[65-58] and 68->INC[68-58]
        self.assertEqual(
            S.income[65 - 58], 3300, msg='No Inflation so should equal configured amount')
        self.assertEqual(
            S.taxed[65 - 58], 300, msg='income.mytaxfree is not taxed but stopgap is so 300')
        expect = 3300 + (36000 + 2400) * 1.025**(68 - 56)
        taxexpect = expect - 3000
        self.assertEqual(
            S.income[68 - 58], expect, msg='Sum of mytaxfree and inflation adjusted rental_1 and rental_2')
        self.assertEqual(
            S.taxed[68 - 58], taxexpect, msg='Same as income minus mytaxfee')
        # TODO Add test cases for the following. Need to convert max and want to single values first
        #self.assertEqual(S.EXP[72 - 58], expect)
        #self.assertEqual(S.MAX[72 - 58], expect)
        #self.assertEqual(S.WANT[72 - 58], expect)

    # TODO add tests for:
    # - get_retiree_info()
    # - do_details()
    # - process_toml_info()


if __name__ == '__main__':
    #add you app's options here...
    # Help:
    # -ctoml filename or --createtomlfile filename
    options_tpl = ('-ctoml', '--createtomlfile')
    del_lst = []
    nameindex = -1
    filename = None
    for i,option in enumerate(sys.argv):
        #print('i/option: ', i, '/', option)
        if i == nameindex:
            filename = option
        if option in options_tpl:
            nameindex = i+1
            del_lst.append(i)
            del_lst.append(i+1) # I don't understand these append(i)

    del_lst.reverse()
    for i in del_lst:
        del sys.argv[i]
    #print('filename: ', filename)
    #print('sys.argv: ', sys.argv)

    if filename is None:
        unittest.main()
    else:
        tf = working_toml_file(filename, skip_file_delete = True)
