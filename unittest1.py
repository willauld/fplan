import sys
import os
import unittest
import vector_var_index as v
import app_output

#from ARetirementPlanner import do_check_index_sequence
#from primes import is_prime
#
#class PrimesTestCase(unittest.TestCase):
#    """Tests for `primes.py`."""
#
#    def test_is_five_prime(self):
#        """Is five successfully determined to be prime?"""
#        self.assertTrue(is_prime(5))
#
class TestIndexes(unittest.TestCase):
    """ Tests to ensure the set of functions index_?() are defined properly """

    def test_index_var_layout_with_aftertax(self):
        """ check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 1, 'aftertax': 1}
        
        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(z)

    def test_index_var_layout_without_aftertax(self):
        """ check that the index_?() are properly laid out in a vector """
        years = 10
        taxbins = 8
        cgbins = 3
        accounts = 4
        accmap = {'IRA': 2, 'roth': 2, 'aftertax': 0}
        
        indx = v.vector_var_index(years, taxbins, cgbins, accounts, accmap)
        z = v.my_check_index_sequence(years, taxbins, cgbins, accounts, accmap, indx)
        self.assertTrue(z)

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

    def test_trueistrue(self):
        """ testing """
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
