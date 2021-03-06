#!/usr/bin/python
#
# Copyright (c) 2012, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import re
import subprocess
import sys
import urllib
import urllib2

EXECUTABLE = 00744
BASE_PATH = '/usr/local/share/PsiphonV'
BLACKLIST_DIR = 'malware_blacklist'
IPSET_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'ipset'))
LIST_DIR = os.path.abspath(os.path.join(BASE_PATH, BLACKLIST_DIR, 'lists'))

LISTS_URL = 'https://s3.amazonaws.com/p3_malware_lists/'

def build_malware_dictionary(url):
    req = urllib2.Request(url)
    malware_dicts = {}
    try:
        resp = urllib2.urlopen(url).read()
        malware_lists = re.findall('\w+\.list', resp)
        for item in malware_lists:
            name = item.split('.')
            malware_dicts[name[0]] = {'url': ''.join([url, item]),
                                     'rawlist': item,
                                     'ipset_file': ''.join([name[0], '.ipset']),
                                     'ip_list': '',
                                     'set_name': name[0],
                                    }
        
    except urllib2.URLError, er:
        if hasattr(er, 'reason'):
            print 'Failed: ', er.reason
        elif hasattr(er, 'code'):
            print 'Error code: ', er.code
    finally:
        return malware_dicts

# Used to update each ip block list
def update_list(tracker):
    print tracker['url']
    # get the file and save it to the outfile location
    try:
        subprocess.call(['mkdir', '-p', LIST_DIR])
        urllib.urlretrieve(tracker['url'], os.path.join(LIST_DIR, tracker['rawlist']))
    except:
        print 'Had an issue creating updating the lists'
        sys.exit()

def parse_ip_list(raw_list_filename, read_mode):
    blackhole_list = []
    with open(os.path.join(LIST_DIR, raw_list_filename), read_mode) as f:
        for line in f:
            if re.search(r"(^#)", line): #find comments
                next
            elif not line.strip(): #remove blank lines
                next
            else:
                blackhole_list.append(line.strip())
    return blackhole_list

# Create the ipset script which includes creating the set name and blocklist
# which is stored in a file for execution
def create_ipset_commands(tracker):
    ipset_base = ["ipset -N %s iphash" % str(tracker['set_name']), 
                  "ipset -F %s" % str(tracker['set_name'])]
    tracker['ipset_rules'] = ipset_base + \
        ["ipset -A %s %s" % (str(tracker['set_name']), str(ip)) for ip in tracker['ip_list']]

def write_ipset_script(tracker):
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(['mkdir', '-p', IPSET_DIR])
    with open(script, 'w') as f:
        for rule in tracker['ipset_rules']:
            f.write('%s\n' % rule)
    os.chmod(script, EXECUTABLE)

def run_ipset_script(tracker):
    script = os.path.join(IPSET_DIR, tracker['ipset_file'])
    subprocess.call(script, shell=True)

def modify_iptables(tracker, opt, chain):
    #iptables command:
    #iptables -D <chain> -m set --set $setname dst -j DROP
    #iptables -I <chain> -m set --set $setname dst -j DROP
    cmd = "iptables %s %s -m set --set %s dst -j DROP" % (opt, chain, tracker['set_name'])
    subprocess.call(cmd, shell=True)

if __name__ == "__main__":
    
    mal_lists = build_malware_dictionary(LISTS_URL)
    
    if mal_lists:
        #lists to use:
        for item in mal_lists:
            update_list(mal_lists[item])
            mal_lists[item]['ip_list'] = parse_ip_list(mal_lists[item]['rawlist'], 'r')
            create_ipset_commands(mal_lists[item])
            write_ipset_script(mal_lists[item])
            run_ipset_script(mal_lists[item])
            modify_iptables(mal_lists[item], '-D', 'OUTPUT')
            modify_iptables(mal_lists[item], '-I', 'OUTPUT')
            modify_iptables(mal_lists[item], '-D', 'FORWARD')
            modify_iptables(mal_lists[item], '-I', 'FORWARD')
    else:
        print 'Malware list is empty, exiting'
        sys.exit()
        
