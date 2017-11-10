import sys

class app_output:
    def __init__(self, file_name):
        self.csv_file = None
        if file_name == '':
            print("\napp_output:File name can not be the empty string.\nIf no CSV file is desired use 'None' for the parameter.")
            exit(1)
        if file_name is not None:
            self.csv_file = open(file_name, 'w')
    
    def __del__(self):
        if self.csv_file is not None and not self.csv_file.closed:
            self.csv_file.close()

    def output(self, string): # TODO move to a better place
        #
        # output writes the information after doing two separate
        # transformations. One for standard out and the other for
        # writing the csv file. 
        # For stdout, all '@' are removed and all '&' replaced with
        # a ' '.
        # For cvs, all '@' are replaced with ',' and all '&' are 
        # removed. 
        # The cvs wrok is done whenever the csv_file handle is not None
        #
        sys.stdout.write(string.replace('@','').replace('&',' '))
        if self.csv_file is not None:
            self.csv_file.write(string.replace('@',',').replace('&',''))
            self.csv_file.flush()