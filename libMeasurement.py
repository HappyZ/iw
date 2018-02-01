#!/usr/bin/python
# -*- coding: utf-8 -*-

import re
import os
import time
import argparse
import subprocess

from numpy import median


def which(program):
    '''
    check if a certain program exists
    '''
    def is_executable(fp):
        return os.path.isfile(fp) and os.access(fp, os.X_OK)
    fp, fn = os.path.split(program)
    if fp:
        if is_executable(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exec_file = os.path.join(path, program)
            if is_executable(exec_file):
                return exec_file
    return None


class Measurement(object):
    def __init__(self, interface, ofp=None, cali=(1.0, 0.0)):
        self.outf = None
        self.interface = interface
        # default file path for config for iw ftm_request
        self.config_fp = '/tmp/config_entry'
        if ofp:
            try:
                self.outf = open(ofp, 'w')
                self.outf.write(
                    'MAC,caliDist(cm),rawRTT(psec),rawRTTVar,rawDist(cm),' +
                    'rawDistVar,rssi(dBm),time(sec)\n'
                )
            except Exception as e:
                print(str(e))
        self.regex = (
            r"Target: (([0-9a-f]{2}:*){6}), " +
            r"status: ([0-9]), rtt: ([0-9\-]+) \(±([0-9\-]+)\) psec, " +
            r"distance: ([0-9\-]+) \(±([0-9\-]+)\) cm, rssi: ([0-9\-]+) dBm"
        )
        self.cali = cali
        if not self.check_iw_validity():
            exit(127)  # command not found

    def check_iw_validity(self):
        '''
        check if iw exists and support FTM commands
        '''
        iwPath = which('iw')
        if iwPath is None:
            print('Err: iw command not found!')
            return False
        p = subprocess.Popen(
            "iw --help | grep FTM",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        out, err = p.communicate()
        if err:
            print('Err: {0}'.format(err))
            return False
        if 'FTM' not in out:
            print('Err: iw command does not support FTM')
            return False
        return True

    def prepare_config_file(self, targets):
        if not isinstance(targets, dict):
            return False
        with open(self.config_fp, 'w') as of:
            for bssid in targets:
                of.write(
                    "{0} bw={1} cf={2} retries={3} asap spb={4}\n".format(
                        bssid,
                        targets[bssid]['bw'],
                        targets[bssid]['cf'],
                        targets[bssid]['retries'],
                        targets[bssid]['spb'],
                    )
                )
        return True

    def get_distance_once(self):
        p = subprocess.Popen(
            "iw wlp58s0 measurement ftm_request " +
            "{0}".format(self.config_fp),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )
        out, err = p.communicate()
        if err:
            print(err)
            exit(13)
        matches = re.finditer(self.regex, out)
        if not matches:
            return []
        result = []
        for match in matches:
            mac = match.group(1)
            status = int(match.group(3))
            rtt = int(match.group(4))
            rtt_var = int(match.group(5))
            raw_distance = int(match.group(6))
            raw_distance_var = int(match.group(7))
            rssi = int(match.group(8))
            if status is not 0 or raw_distance < -1000:
                continue
            distance = self.cali[0] * raw_distance + self.cali[1]
            result.append((mac, distance, rtt, raw_distance))
            if self.outf is not None:
                self.outf.write(
                    "{0},{1:.2f},{2},{3},{4},{5},{6},{7:.6f}\n".format(
                        mac, distance, rtt, rtt_var,
                        raw_distance, raw_distance_var,
                        rssi, time.time()
                    )
                )
        return result

    def get_distance_median(self, rounds=1):
        '''
        use median instead of mean for less bias with small number of rounds
        '''
        result = {}
        median_result = {}
        if rounds < 1:
            rounds = 1
        for i in range(rounds):
            # no guarantee that all rounds are successful
            for each in self.get_distance_once():
                if each[0] not in result:
                    result[each[0]] = []
                result[each[0]].append(each[1:])
        for mac in result:
            median_result[mac] = median([x[0] for x in result[mac]])
        return median_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # properly close the file when destroying the object
        if self.outf is not None:
            self.outf.close()


def wrapper(args):
    args['config_entry'] = {
        '34:f6:4b:5e:69:1f': {
            'bw': 20,
            'cf': 2462,
            'spb': 255,
            'retries': 3
        }
    }
    counter = 1
    with Measurement(
        args['interface'],
        ofp=args['filepath'], cali=args['cali']
    ) as m:
        while 1:
            print('Round {0}'.format(counter))
            try:
                m.prepare_config_file(args['config_entry'])
                # only print out results
                results = m.get_distance_median(rounds=args['rounds'])
                for mac in results:
                    print('* {0} is {1:.4f}cm away.'.format(mac, results[mac]))
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(str(e))
                break
            counter += 1


def main():
    p = argparse.ArgumentParser(description='iw measurement tool')
    p.add_argument(
        '--cali',
        nargs=2,
        # default=(0.9234, 534.7103),  # indoor
        default=(0.8324, 583.7435),  # outdoor
        type=float,
        help="calibrate final result"
    )
    p.add_argument(
        '--filepath', '-f',
        default=None,
        help="if set, will write raw fetched data to file"
    )
    p.add_argument(
        '--rounds',
        default=3,
        type=int,
        help="how many rounds to run one command; default is 3"
    )
    p.add_argument(
        '--interface', '-i',
        default='wlp58s0',
        help="set the wireless interface"
    )
    try:
        args = vars(p.parse_args())
    except Exception as e:
        print(str(e))
        sys.exit()
    args['time_of_exec'] = int(time.time())
    # rename file path by adding time of exec
    if args['filepath']:
        fp, ext = os.path.splitext(args['filepath'])
        args['filepath'] = "{0}_{1}{2}".format(fp, args['time_of_exec'], ext)
    wrapper(args)


if __name__ == '__main__':
    main()
