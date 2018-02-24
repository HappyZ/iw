#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time
import math
import argparse

from math import sin, cos, sqrt, atan2, radians
from numpy import median, arange

R = 6373000.0  # unit: meter

# ======= start =======
# excerpt from
# https://github.com/noomrevlis/trilateration/blob/master/trilateration2D.py


class Point(object):
    def __init__(self, x, y):
        self.x = round(float(x), 6)
        self.y = round(float(y), 6)


class Circle(object):
    def __init__(self, p, radius):
        if isinstance(p, Point):
            self.center = p
        elif isinstance(p, list):
            self.center = Point(p[0], p[1])
        self.radius = round(float(radius), 6)


def get_distance(p1, p2):
    if isinstance(p1, Point) and isinstance(p2, Point):
        return math.sqrt(
            (p1.x - p2.x) * (p1.x - p2.x) +
            (p1.y - p2.y) * (p1.y - p2.y)
        )
    elif (
        (isinstance(p1, list) or isinstance(p1, tuple)) and
        (isinstance(p2, list) or isinstance(p2, tuple))
    ):
        return math.sqrt(
            (p1[0] - p2[0]) * (p1[0] - p2[0]) +
            (p1[1] - p2[1]) * (p1[1] - p2[1])
        )
    return -1


def get_distance_gps(p1, p2, isDeg=True):
    # format: p1 ~ p2 = [lat, lon] in deg
    if (
        (isinstance(p1, list) or isinstance(p1, tuple)) and
        (isinstance(p2, list) or isinstance(p2, tuple))
    ):
        if isDeg:
            lat1 = radians(p1[0])
            lon1 = radians(p1[1])
            lat2 = radians(p2[0])
            lon2 = radians(p2[1])
        else:
            lat1 = (p1[0])
            lon1 = (p1[1])
            lat2 = (p2[0])
            lon2 = (p2[1])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c
    return -1


def get_two_circles_intersecting_points(c1, c2):
    p1 = c1.center
    p2 = c2.center
    r1 = c1.radius
    r2 = c2.radius

    d = get_distance(p1, p2)
    # if to far away, or self contained - can't be done
    if d >= (r1 + r2) or d <= math.fabs(r1 - r2):
        return None

    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(pow(r1, 2) - pow(a, 2))
    x0 = p1.x + a*(p2.x - p1.x)/d
    y0 = p1.y + a*(p2.y - p1.y)/d
    rx = -(p2.y - p1.y) * (h/d)
    ry = -(p2.x - p1.x) * (h / d)
    return [
        Point(x0 + rx, y0 - ry),
        Point(x0 - rx, y0 + ry)
    ]


def get_intersecting_points(circles):
    points = []
    num = len(circles)
    for i in range(num):
        j = i + 1
        for k in range(j, num):
            res = get_two_circles_intersecting_points(circles[i], circles[k])
            if res:
                points.extend(res)
    return points


def is_contained_in_circles(point, circles):
    for i in range(len(circles)):
        if (
            get_distance(point, circles[i].center) > circles[i].radius
        ):
            return False
    return True


def get_polygon_center(points):
    center = Point(float('nan'), float('nan'))
    xs = []
    ys = []
    num = len(points)
    if num is 0:
        return center
    for i in range(num):
        xs.append(points[i].x)
        ys.append(points[i].y)
    center.x = median(xs)
    center.y = median(ys)
    return center
# ======= end =======


def calcInnerPoints(circles, bounds):
    inner_points = []
    for p in get_intersecting_points(circles):
        # if not is_contained_in_circles(p, circles):
        #     continue
        if bounds is not None:
            if bounds.get('x_min', None) is not None and bounds['x_min'] > p.x:
                continue
            if bounds.get('x_max', None) is not None and bounds['x_max'] < p.x:
                continue
            if bounds.get('y_min', None) is not None and bounds['y_min'] > p.y:
                continue
            if bounds.get('y_max', None) is not None and bounds['y_max'] < p.y:
                continue
        inner_points.append(p)
    return inner_points


def trilateration2d(mydict, bounds=None, verbose=False):
    '''
    mydict format: {
        location: (radius, std),...
    }
    bound format: {
        'x_min': float, 'x_max': float,
        'y_min': float, 'y_max': float
    }
    '''
    points = []
    circles = []
    for loc in mydict:
        tmp = loc.split(',')
        p = Point(tmp[0], tmp[1])
        points.append(p)
        if mydict[loc][1]:
            for r in arange(
                max(mydict[loc][0] - mydict[loc][1], 0.001),
                mydict[loc][0] + mydict[loc][1],
                1
            ):
                circles.append(Circle(p, r))
        else:
            circles.append(Circle(p, mydict[loc][0]))
    inner_points = calcInnerPoints(circles, bounds)
    if verbose:
        print('* Inner points:')
        if len(inner_points) is 0:
            print('*** No inner points detected!!')
        for point in inner_points:
            print('*** ({0:.3f}, {1:.3f})'.format(point.x, point.y))
    center = get_polygon_center(inner_points)
    return (center.x, center.y)


def deriveLocation(args, results):
    # TODO: currently assume 2D
    loc_distance = {}
    for mac in results:
        if mac not in args['config_entry']:
            continue
        loc = args['config_entry'][mac].get('location', None)
        if loc is None:
            continue
        loc_distance[loc] = results[mac]
    loc = trilateration2d(
        loc_distance,
        bounds=args.get('loc_bounds', None),
        verbose=args.get('verbose', False)
    )
    if args.get('outfp', False):
        with open("{0}_locs".format(args['outfp']), 'a') as f:
            f.write(
                "{0:.6f},{1:.4f},{2:.4f}\n"
                .format(time.time(), loc[0], loc[1])
            )
    return loc


def plotLocation(loc):
    handler = None
    try:
        import matplotlib.pyplot as plt
        handler = plt.scatter(loc[0], loc[1])
        plt.pause(0.01)
    except Exception:
        pass
    return handler


if __name__ == '__main__':
    dist = get_distance_gps([41.790366, -87.601111], [41.790609, -87.601411])
    print(dist)
    # loc = deriveLocation(
    #     {
    #         'config_entry': {
    #             '34:f6:4b:5e:69:1f': {'location': '0,0'},
    #             '34:f6:4b:5e:69:1e': {'location': '180,0'},
    #             '34:f6:4b:5e:69:1d': {'location': '0,2'},
    #             '34:f6:4b:5e:69:1a': {'location': '1,2'}
    #         },
    #         'verbose': True,
    #         'outfp': '',
    #         'loc_bounds': {
    #             'y_min': 0
    #         }
    #     },
    #     {
    #         '34:f6:4b:5e:69:1f': (257, 0),
    #         '34:f6:4b:5e:69:1e': (50, 50)
    #     }
    # )
    # flagPlot = False
    # try:
    #     import matplotlib.pyplot as plt
    #     flagPlot = True
    # except Exception:
    #     pass
    # if flagPlot:
    #     fig = plt.figure()
    #     plt.ion()
    #     plt.xlim([-100, 300])
    #     plt.ylim([-10, 500])
    #     while 1:
    #         try:
    #             handler = plotLocation(loc)
    #             if handler is None:
    #                 plt.close(fig)
    #                 break
    #             handler.remove()
    #         except KeyboardInterrupt:
    #             plt.close(fig)
    #             break
    #         except Exception:
    #             raise
