# Retirement planner

This is a retirement planner application designed to explore
optimial withdrawals from retirement accounts while accounting for
other income, social security and federal taxes. It uses a Linear
Programming solution to maximize the amount of money available
for yearly spending assuming spending goes up with inflation.

This project started with Wayne Scott's https://github.com/wscott/fplan 
though at this point the model is compeletly different while making 
very similar calculations. 

This is similar to the ideas of James Welch at www.i-orp.com and as Wayne
wanted to explore some new ideas so have I. I have looked to both projects
for insperation. 

ORP continues to be a much more complete tool. 

## Currently modeled

* Joint retirement (retirement accounts and social security for a couple)
* aftertax, IRA and Roth account withdrawals for spending
* aftertax, IRA and Roth account deposits 
* Federal income and capital gains tax with 2017 tables
* Assumes an average cost basis that shrinks over time (looking to improve this)
* (not correct) Roth withdraw limitations before age 59
* Early IRA withdrawals have a 10% penalty
* inflation
* Required Minimum Distributions from IRA
* Arbitrary income or expenses happening at certain years. Income can
  be taxed or not.  
* Social Security assuming the maximum percentage is taxed (85%)
* Social Security sposal benefit

## Not modeled yet

* IRA->Roth conversions
* IRA 72(t) withdrawals
* Early withdrawals from Roth gains are not modeled (only contributions)
* Recording when existing Roth contributions can be accessed in config file

## Not modeled

* State taxes

## Assumptions

* Taxes are only for Married filing jointly at the moment
* Standard deductions and exemptions 
* Assumed to be past 59.5 only by age 60

## Installing

This program is written in Python3 and assumes the packages SciPy and
toml are installed.

run `pip install --user toml scipy numpy` to install these libraries
on most machines.

## Usage

* Copy `ARetirementPlannerJointExample.toml` to a new file
* Edit with your information
* run `python3 ./ARetirementPlanner.py NEW.toml`


* run `python3 ./ARetirementPlanner.py -h` for help

PS C:\home\fplan> python .\ARetirementPlanner.py -h
usage: ARetirementPlanner.py [-h] [-v] [-va] [-vt] [-vtb] [-vw] [-vm] [-mall]
                             [-csv]
                             conffile
positional arguments:
  conffile

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         Extra output from solver
  -va, --verboseaccounttrans
                        Output detailed account transactions from solver
  -vt, --verbosetax     Output detailed tax info from solver
  -vtb, --verbosetaxbrackets
                        Output detailed tax bracket info from solver
  -vw, --verbosewga     Extra wga output from solver
  -vm, --verbosemodel   Output the binding constraints of the LP model
  -mall, --verbosemodelall
                        Output the entire LP model - not just the binding
                        constraints
  -csv, --csv           Additionally write the output from to a csv file

## Output

The standard output is a table by age with the following columns. In cases 
where there are two different acount owners the data is combined in this 
table but split out in the optional account transaction summary table. All 
numbers in table are in 1000s of dollars except those for the tax brackets 
in optional output. Additional details are available with the appropriate 
application switches.

* fIRA: amount to withdrawal from IRA(s) this year
* tIRA: amount to deposit to IRA(s) this year
* RMDref: Required Minimum Distribution(s) (given only as a reference)
* fRoth: amount to withdrawal from Roth(s) this year
* tRoth: amount to deposit to Roth(s) this year
* fAftaTx: amount to withdrawal from After tax account(s) this year
* tAftaTx: amount to deposit to After tax account(s) this year
* o_inc: Other income as defined in the configuration file
* SS: Social Security income
* Expense: Short term expenses as defined in the configuration file
* TFedTax: Total Federal Tax including income tax, early withdrawal penalties, capital gains tax
* Spndble: The maximum spendable amount after taxes


This tool is being actively developed and eventually will, I hope, 
have a much more user-friendly inteface. At the moment it is mostly
a prototyping tool. 

