import unittest
import vector_var_index as v

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

    def test_trueistrue(self):
        """ testing """
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
