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
        # output writes the information after first changing any '@' in the string
        # to a space for stdout or a ',' for csv files. The later is written
        # whenever the csv_file handle is not None
        #
        sys.stdout.write(string.replace('@',' '))
        if self.csv_file is not None:
            self.csv_file.write(string.replace('@',','))
            self.csv_file.flush()