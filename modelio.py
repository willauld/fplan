
import os
from array import array


def checkDump(c, A, b):
    with open("./wson_c", 'r') as input_file:
        indx = -1
        for line in input_file:
            line = line.strip()
            if indx == -1:
                print("./wson_c first line is: %s" % line)
                indx += 1
                continue
            if c[indx] != float(line):
                print("c[%d] is %g but found %g" %
                      (indx, c[indx], float(line)))
            indx += 1
        print("c index is %d" % indx)
    with open("./wson_b", 'r') as input_file:
        indx = -1
        for line in input_file:
            line = line.strip()
            if indx == -1:
                print("./wson_b first line is: %s" % line)
                indx += 1
                continue
            if b[indx] != float(line):
                print("b[%d] is %g but found %g" %
                      (indx, b[indx], float(line)))
            indx += 1
        print("b index is %d" % indx)
    with open("./wson_A", 'r') as input_file:
        indx = -2
        for line in input_file:
            line = line.strip()
            if indx < 0:
                print("./wson_A line is: %s" % line)
                columns = int(line)  # second assignment is columns :-)
                indx += 1
                continue
            a = indx // columns
            b = indx % columns
            if A[a][b] != float(line):
                print("indx %d, A[%d][%d] is %g but found %g" %
                      (indx, a, b, A[a][b], float(line)))
            indx += 1
        print("A index is %d" % indx)
        # for number in line.split():
        #    yield float(number)


def binDumpCheck(c, A, b, X, vid, ftocheck):
    fsize = os.path.getsize(ftocheck)

    overheads = 3
    sizeX = 0
    if X is not None:
        sizeX = 8 * len(X)
        overheads += 1

    sizevid = 0
    if vid is not None:
        sizevid = 4 * len(vid)
        overheads += 1

    if fsize != overheads * 12 + 8 * len(c) + 8 * len(A) * len(A[0]) + 8 * len(b) + sizeX + sizevid:
        print('Error - dump file size error, filesize: %d, len(c): %d, len(A): %d, Len(A[0]): %d, len(b): %d, sizeX: %d, sizevid: %d' % (
            fsize, len(c), len(A), len(A[0]), len(b), sizeX, sizevid))

    c1, A1, b1, X1, vid1 = binLoadModel(ftocheck)

    # Check loaded C vector
    if len(c) != len(c1):
        print("modelio error: len(c): %d does not match len(c1) %d" %
              (len(c), len(c1)))
    for i in range(len(c)):
        if c[i] != c1[i]:
            print("c[%d] is %g but found %g" % (i, c[i], c1[i]))

    # Checking A matrix
    if len(A) != len(A1):
        print("modelio error: len(A): %d does not match len(A1) %d" %
              (len(A), len(A1)))
    for i in range(len(A)):
        if len(A[0]) != len(A1[i]):
            print("modelio error: len(A[0]): %d does not match len(A1[%d]) %d" % (
                i, len(A[0]), len(A1[i])))
        for j in range(len(A[0])):
            if A[i][j] != A1[i][j]:
                print("A[%d][%d] is %g but found %g" %
                      (i, j, A[i][j], A1[i][j]))

    # Checking b vector
    if len(b) != len(b1):
        print("modelio error: len(b): %d does not match len(b1) %d" %
              (len(b), len(b1)))
    for i in range(len(b)):
        if b[i] != b1[i]:
            print("b[%d] is %g but found %g" % (i, b[i], b1[i]))

    # Checking X vector
    if X is not None:
        if len(X) != len(X1):
            print("modelio error: len(X): %d does not match len(X1) %d" %
                  (len(X), len(X1)))
        for i in range(len(X)):
            if X[i] != X1[i]:
                print("X[%d] is %g but found %g" % (i, X[i], X1[i]))

    # Checking vid vector
    if vid is not None:
        if len(vid) != len(vid1):
            print("modelio error: len(vid): %d does not match len(vid1) %d" %
                  (len(vid), len(vid1)))
        for i in range(len(vid)):
            if vid[i] != vid1[i]:
                print("vid[%d] is %d but found %d" % (i, vid[i], vid1[i]))


def binLoadModel(filename=None):
    if filename is None:
        filename = "./RPlanModel.dat"
    fsize = os.path.getsize(filename)
    with open(filename, 'rb') as input_file:

        # Load c
        hArray = array('L')  # 12 bytes or 3 longs 4 bytes each
        float_array = array('d')  # 8 bytes each
        hArray.fromfile(input_file, 3)  # Header always 3 longs
        #print("Loaded Header: length %d, width %d, code %d" % (hArray[0], hArray[1], hArray[2]))
        if hArray[2] != 0xDEADBEEF:
            print('Header Error: header does not have 0xDEADBEAF at the correct place.')
        if hArray[1] != 0:  # Reading an array
            print("Error - Vector C should not have a width")
        #print("loadsize: %d" % hArray[0])
        float_array.fromfile(input_file, hArray[0])
        c = float_array
        #print("len(C from file): %d" % len(float_array))

        # Load A matrix
        hArray = array('L')  # 12 bytes or 3 longs 4 bytes each
        float_array = array('d')  # 8 bytes each
        hArray.fromfile(input_file, 3)  # Header always 3 longs
        #print("Loaded Header: length %d, width %d, code %d" % (hArray[0], hArray[1], hArray[2]))
        if hArray[2] != 0xDEADBEEF:
            print(
                'Line 715: Header Error: header does not have 0xDEADBEAF at the correct place.')
        if hArray[1] == 0:  # Reading an array
            print("Load A[][] header incorrect with 0 column width")
        Aprime = []
        #print("loadsize: rows %d, cols %d" % (hArray[0], hArray[1]))
        for i in range(hArray[0]):
            #print("Laoding row %d" % i)
            float_array = array('d')  # 8 bytes each
            float_array.fromfile(input_file, hArray[1])
            Aprime += [float_array]
            # float_array=[]
        A = Aprime

        # Load b vector
        hArray = array('L')  # 12 bytes or 3 longs 4 bytes each
        float_array = array('d')  # 8 bytes each
        hArray.fromfile(input_file, 3)  # Header always 3 longs
        if hArray[2] != 0xDEADBEEF:
            print('b Header Error: header does not have 0xDEADBEAF at the correct place.')
        if hArray[1] != 0:  # Reading an array
            print("Error - Vector b should not have a width")
        float_array.fromfile(input_file, hArray[0])
        b = float_array
        overheads = 3

        # Load X
        hArray = array('L')  # 12 bytes or 3 longs 4 bytes each
        float_array = array('d')  # 8 bytes each
        try:
            hArray.fromfile(input_file, 3)  # Header always 3 longs
            #print("Loaded Header: length %d, width %d, code %d" % (hArray[0], hArray[1], hArray[2]))
            if hArray[2] != 0xDEADBEEF:
                print(
                    'Header Error: X header does not have 0xDEADBEAF at the correct place.')
            if hArray[1] != 0:  # Reading an array
                print("Error - Vector X should not have a width")
            #print("loadsize: %d" % hArray[0])
            float_array.fromfile(input_file, hArray[0])
            X = float_array
            sizeX = 8 * len(X)
            overheads += 1
            #print("len(C from file): %d" % len(float_array))
        except EOFError:
            X = None
            sizeX = 0
            print('Why did you do an EOF on me?')

        # Load vid
        hArray = array('L')  # 12 bytes or 3 longs 4 bytes each
        int_array = array('l')  # 4 bytes each
        try:
            hArray.fromfile(input_file, 3)  # Header always 3 longs
            #print("Loaded Header: length %d, width %d, code %d" % (hArray[0], hArray[1], hArray[2]))
            if hArray[2] != 0xDEADBEEF:
                print(
                    'Header Error: VID header does not have 0xDEADBEAF at the correct place.')
            if hArray[1] != 0:  # Reading an array
                print("Error - Vector VID should not have a width")
            #print("loadsize: %d" % hArray[0])
            int_array.fromfile(input_file, hArray[0])
            vid = int_array
            sizevid = 4 * len(vid)
            overheads += 1
            #print("len(C from file): %d" % len(float_array))
        except EOFError:
            vid = None
            sizevid = 0
            print('Why did you do an EOF on me?')

    if fsize != overheads * 12 + 8 * len(c) + 8 * len(A) * len(A[0]) + 8 * len(b) + sizeX + sizevid:
        print('Error - load file size error, filesize: %d, len(c): %d, len(A): %d, Len(A[0]): %d, len(b): %d, sizeX: %d, sizevid: %d' % (
            fsize, len(c), len(A), len(A[0]), len(b), sizeX, sizevid))
    return c, A, b, X, vid


def binDumpModel(c, A, b, X, vid, fname=None):
    if fname is None:
        fname = "./RPlanModel.dat"
    stream = open(fname, 'wb')

    header = [len(c), 0, 0xDEADBEEF]
    hArray = array('L', header)
    hArray.tofile(stream)
    print("c length: %d, dumping" % len(c))
    a = array('d', c)
    a.tofile(stream)

    header = [len(A), len(A[0]), 0xDEADBEEF]
    hArray = array('L', header)
    hArray.tofile(stream)
    print("A length: %d, %d, dumping" % (len(A), len(A[0])))
    for row in A:
        a = array('d', row)
        a.tofile(stream)

    header = [len(b), 0, 0xDEADBEEF]
    hArray = array('L', header)
    hArray.tofile(stream)
    print("b length: %d, dumping" % len(b))
    a = array('d', b)
    a.tofile(stream)

    overheads = 3
    sizeX = 0
    if X is not None:
        header = [len(X), 0, 0xDEADBEEF]
        hArray = array('L', header)
        hArray.tofile(stream)
        print("X length: %d, dumping" % len(X))
        a = array('d', X)
        a.tofile(stream)
        sizeX = 8 * len(X)
        overheads += 1

    sizevid = 0
    if vid is not None:
        header = [len(vid), 0, 0xDEADBEEF]
        hArray = array('L', header)
        hArray.tofile(stream)
        print("vid length: %d, dumping" % len(vid))
        a = array('l', vid)
        a.tofile(stream)
        sizevid = 4 * len(vid)
        overheads += 1

    stream.flush()
    stream.close()

    fsize = os.path.getsize(fname)
    calcsize = overheads * 12 + 8 * \
        len(c) + 8 * len(A) * len(A[0]) + 8 * len(b) + sizeX + sizevid
    if fsize != calcsize:
        print('Error - dump file size error, filesize: %d, len(c): %d, len(A): %d, Len(A[0]): %d, len(b): %d, sizeX: %d, sizevid: %d' % (
            fsize, len(c), len(A), len(A[0]), len(b), sizeX, sizevid))
    binDumpCheck(c, A, b, X, vid, fname)


def dumpModel(c, A, b):
    fil = open('./wson_c', 'w+')
    print('%d' % len(c), file=fil)
    for val in c:
        print('%g' % val, file=fil)
    fil.close()
    fil = open('./wson_b', 'w+')
    print('%d' % len(b), file=fil)
    for val in b:
        print('%g' % val, file=fil)
    fil.close()
    fil = open('./wson_A', 'w+')
    print('%d' % len(A), file=fil)
    print('%d' % len(A[0]), file=fil)
    for r in A:
        for val in r:
            print('%g' % val, file=fil)
    fil.close()
    # checkDump(c,A,b)
