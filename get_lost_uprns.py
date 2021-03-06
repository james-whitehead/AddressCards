"""
Looks up UPRNs that were left out of batches because the swapping around
of list indexes only work if UPRNs are groueped into lists of four.
Any UPRNs that fall after the last group of four are skipped because an
IndexError is thrown

NOTE:
    When saving the result of a query from MSSQL, the UPRN is treated as an
    integer if opened in Excel so the leading zero is removed.
"""

import csv
import os

# Get a list of processed UPRNs from the ./out directory
files = [f for f in os.listdir('./out')if f.endswith('-addr.jpg')]
trimmed = []
for f in files:
    trimmed.append(f[:-9])
proc_uprns = []
for trim in trimmed:
    proc_uprns.append(trim.split('-'))
proc_uprns = [uprn for sublist in proc_uprns for uprn in sublist]
# Get a list of every UPRN in the batch from the CSV
batch_uprns = []
with open ('./fourth_batch.csv') as csv_file:
    csv_read = csv.reader(csv_file)
    for row in csv_read:
        batch_uprns.append(row[0])
# Get the difference between the two lists
uprn_set = set(proc_uprns)
uprn_diff = [uprn for uprn in batch_uprns if uprn not in uprn_set]
print(uprn_diff)
