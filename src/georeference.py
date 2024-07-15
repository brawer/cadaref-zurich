# mutation: HG3099
# parcel: HG7698
# topleft:  2678576.67, 1251928.47
# botright: 2678672.85, 1251798.69

from collections import namedtuple
import csv
import json
import math
import os
import rasterio
from rasterio.control import GroundControlPoint
import rasterio.plot
import rasterio.transform

import cv2
import numpy
import PIL.Image
import quads

from classify import classify_contour

# Ground Control Points: Border points
HGD4867 = ('HGD4867', 2678627.89, 1251882.92)  # white circle
HGE4867 = ('HGE4867', 2678644.58, 1251853.03)  # white circle
HGG4866 = ('HGG4866', 2678612.35, 1251849.40)  # white circle
HGN4862 = ('HGN4862', 2678624.15, 1251853.03)  # black dot

# Ground Control Points: LFP3
# HG2803 = ('HG2803', 2678640.03, 1251845.94)  # double white circle


LV95 = rasterio.crs.CRS.from_epsg(2056)  # epsg.io/2056

BorderPoint = namedtuple("BorderPoint", "id type style x y")
FixedPoint = namedtuple("FixedPoint", "id type protection style x y")

# rasterio.transform.from_gcp

class Referencer(object):
    def __init__(self):
        self._read_points()
        self._read_parcels()

    def process(self, mutation):
        rendered_path = os.path.join("rendered", "%s.tif" % mutation)
        thresholded_path = os.path.join("thresholded", "%s.tif" % mutation)
        rendered = PIL.Image.open(rendered_path)
        thresholded = PIL.Image.open(thresholded_path)
        assert rendered.n_frames == thresholded.n_frames, mutation
        for page_num in range(rendered.n_frames):
            # TODO: Detect if the page is a plan or something else,
            # probably in a separate phase. Then, only process pages
            # that have been classified as plans.
            if page_num != 0:
                continue
            rendered.seek(page_num)
            thresholded.seek(page_num)
            scale_x = float(rendered.size[0]) / thresholded.size[0]
            scale_y = float(rendered.size[1]) / thresholded.size[1]
            scale = (scale_x, scale_y)
            dpi = thresholded.info["dpi"][0]
            meta = json.loads(thresholded.tag_v2[270])
            page_center = self._guess_page_center(meta)
            if not page_center:
                print("cannot guess page center:", mutation)
                continue
            transform = self.find_transform(thresholded, rendered, page_center)
            if transform is None:
                continue                
            rendered_img = numpy.asarray(rendered)
            if page_num == 0:
                out_filename = "%s.tif" % mutation
            else:
                out_filename = "%s_%d.tif" % (mutation, page_num + 1)
            out_path = os.path.join("georeferenced", out_filename)
            with rasterio.open(
                    out_path,
                    'w',
                    driver='GTiff',
                    height=rendered_img.shape[0],
                    width=rendered_img.shape[1],
                    count=rendered_img.shape[2],
                    dtype=rendered_img.dtype,
                    crs=LV95,
                    transform=transform) as out:
                reshaped = rasterio.plot.reshape_as_raster(rendered_img)
                out.write(reshaped)
            print(out_path)

    def _find_map_points(self, thresh):
        contours, hierarchy = cv2.findContours(
            thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS
        )
        result = []
        for c, contour in enumerate(contours):
            if klass := classify_contour(thresh, contours, hierarchy, c):
                x, y, w, h = cv2.boundingRect(contour)
                x, y = (x + w / 2, y + h / 2)
                result.append((x, y, klass))
        result.sort()
        return result

    @staticmethod
    def _get_dpi_scale(thresholded, rendered):
        (rx, ry), (tx, ty) = rendered.info["dpi"], thresholded.info["dpi"]
        return float(rx) / float(tx), float(ry) / float(ty)

    def find_transform(self, thresholded, rendered, page_center):
        img = numpy.asarray(thresholded).astype(numpy.uint8) * 255
        map_points = self._find_map_points(img)
        # TODO: Remove filtering, this is just for debugging.
        map_points = [p for p in map_points if p[2] == "double_white_circle"]
        if len(map_points) < 3:
            return None
        
        scale_x, scale_y = self._get_dpi_scale(thresholded, rendered)
        dpi = float(thresholded.info["dpi"][0])
        for map_scale in (500, 1000,):  # TODO: from OCR?
            pixels_to_meters = (map_scale / 100.0) * 2.54 / dpi
            width_meters = thresholded.width * pixels_to_meters
            height_meters = thresholded.height * pixels_to_meters
            search_meters = max(width_meters, height_meters) * 1.3
            bbox = quads.BoundingBox(
                min_x=page_center[0] - search_meters,
                max_x=page_center[0] + search_meters,
                min_y=page_center[1] - search_meters,
                max_y=page_center[1] + search_meters,
            )
            geo_points = self.points.within_bb(bbox)
            # TODO: Remove filtering, this is just for debugging.
            #geo_points = [p.data for p in geo_points if p.data.style == "double_white_circle"]
            if len(geo_points) < 3:
                continue

            print('-------', map_scale)
            print(len(geo_points), len(map_points))
            tolerance = 0.4  # meters
            for mi in range(len(map_points) - 1):
                p = map_points[mi]
                print("p:", p)
                for mj in range(mi+1, len(map_points)):
                    q = map_points[mj]
                    dx, dy = p[0] - q[0], p[1] - q[1]
                    dist_pq = math.sqrt(dx*dx + dy*dy) * pixels_to_meters
                    min_dist_ab_sq = (dist_pq - tolerance) ** 2
                    max_dist_ab_sq = (dist_pq + tolerance) ** 2
                    for aa in range(len(geo_points)):
                        a = geo_points[aa].data
                        if p[2] != a.style: continue
                        #if a.id != 'HG2805': continue
                        for bb in range(len(geo_points)):
                            if aa == bb:
                                continue
                            b = geo_points[bb].data
                            if q[2] != b.style:
                                continue
                            dist_ab_sq = dist_sq(a, b)
                            dist_ab = math.sqrt(dist_ab_sq)
                            if min_dist_ab_sq <= dist_ab_sq <= max_dist_ab_sq:
                                print("*** LEU a=%s b=%s p=(%d,%d) q=(%d,%d) Δab=%.1f Δpq=%.1f" % (a.id, b.id, int(p[0]), int(p[1]), int(q[0]), int(q[1]), dist_ab, dist_pq))
                        #for b in self._points_on_circle(a.x, a.y, dist_pq):
                        #    print("*** LEU.found", b)
                        #print("*** LEU", mi, mj, k, pi, pj, pk)
                        #print("*** LEU.distance:", 
                        #return None
        return None
        
        px, py = self.double_white_circles['HG2803']
        rx, ry = 3364, 4363
        a = GroundControlPoint(col=rx*scale_x, row=ry*scale_y, x=px, y=py)

        px, py = self.double_white_circles['HG2804']
        rx, ry = 3629, 2243
        b = GroundControlPoint(col=rx*scale_x, row=ry*scale_y, x=px, y=py)

        px, py = self.double_white_circles['HG2805']
        rx, ry = 207, 3475
        c = GroundControlPoint(col=rx*scale_x, row=ry*scale_y, x=px, y=py)

        transform = rasterio.transform.from_gcps([a, b, c])
        return transform

    def _guess_transforms(self, dpi):
        pass
    

    def _guess_page_center(self, meta):
        min_x, max_x, min_y, max_y = 1e9, 0.0, 1e9, 0.0
        for parcel_id in meta['parcels']:
            if box := self.parcels.get(parcel_id):
                min_x, max_x = min(min_x, box[0]), max(max_x, box[1])
                min_y, max_y = min(min_y, box[2]), max(max_y, box[3])
        if max_x == 0.0:
            return None
        center_x = min_x + (max_x - min_x) / 2.0
        center_y = min_y + (max_y - min_y) / 2.0
        return (center_x, center_y)

    def _read_parcels(self):
        self.parcels = {}
        with open('parcels.csv', 'r') as csvfile:
            for row in csv.DictReader(csvfile):
                id = row['parcel']
                x0, x1 = float(row['min_x']), float(row['max_x'])
                y0, y1 = float(row['min_y']), float(row['max_y'])
                self.parcels[id] = (x0, x1, y0, y1)

    def _read_points(self):
        points = []
        with open('border_points.csv', 'r') as csvfile:
            for row in csv.DictReader(csvfile):
                point_type = row['type']
                style = {
                    "unversichert": "black_dot",
                    "Bolzen": "white_circle",
                    "Stein": "white_circle",
                }.get(point_type)
                p = BorderPoint(
                    id=row["point"],
                    type=point_type,
                    style=style,
                    x=float(row["x"]),
                    y=float(row["y"]),
                )
                points.append(p)
        with open('fix_points.csv', 'r') as csvfile:
            for row in csv.DictReader(csvfile):
                p = FixedPoint(
                    id=row["point"],
                    type=row["type"],
                    protection=row["protection"],
                    style="double_white_circle",
                    x=float(row["x"]),
                    y=float(row["y"]),
                )
                points.append(p)
        min_x = min(p.x for p in points)
        max_x = max(p.x for p in points)
        min_y = min(p.y for p in points)
        max_y = max(p.y for p in points)
        width = max_x - min_x
        height = max_y - min_y
        center_x = min_x + width / 2.0
        center_y = min_y + height / 2.0
        self.points = quads.QuadTree(
            center=(center_x, center_y),
            width=width + 1,
            height=height + 1,
        )
        for p in points:
            self.points.insert((p.x, p.y), data=p)

def process(mutation):
    thresholded_path = os.path.join("thresholded", "%s.tif" % mutation)
    scale = (0.5, 0.5)  # 600->300 dpi thresholded->rendered; both x and y
    with PIL.Image.open(thresholded_path) as tiff:
        for page_num in range(tiff.n_frames):
            tiff.seek(page_num)
            img = numpy.asarray(tiff)
            gcp = georeference(img, scale)
            write_plan(mutation, page_num, gcp)
            out_path = os.path.join('georeferenced', out_filename)

            
def dist_sq(a, b):
    delta_x = a.x - b.x
    delta_y = a.y - b.y
    return delta_x * delta_x + delta_y * delta_y


def georeference(img, scale):
    scale_x, scale_y = scale
    
    height, width = int(img.shape[0]*scale_y+0.5), int(img.shape[1]*scale_x+0.5)
    min_x, max_x = 2678576.67, 2678672.85
    min_y, max_y = 1251798.69, 1251928.47
    assert min_x < max_x
    assert min_y < max_y
    #print("*** width: %d height %d" % (width, height))
    #top_left = GroundControlPoint(row=0, col=0, x=min_x, y=max_y)
    #top_right = GroundControlPoint(row=0, col=width-1, x=max_x, y=max_y)
    #bottom_left = GroundControlPoint(row=height-1, col=0, x=min_x, y=min_y)
    #return [top_left, top_right, bottom_left]
    




def write_plan(mutation, page_num, points):
    rendered_path = os.path.join('rendered', "%s.tif" % mutation)
    if page_num == 0:
        out_filename = "%s.tif" % mutation
    else:
        out_filename = "%s_%d.tif" % (mutation, page_num + 1)
    out_path = os.path.join('georeferenced', out_filename)
    with PIL.Image.open(rendered_path) as tiff:
        tiff.seek(page_num)
        #x_dpi, y_dpi = tiff.info["dpi"]
        meta = json.loads(tiff.tag_v2.get(270))
        image = numpy.asarray(tiff)
    transform = rasterio.transform.from_gcps(points)
    print("Transform:", transform)
    for n, p in enumerate(points):
        print("point[%d] = %s" % (n, p))
    with rasterio.open(
            out_path,
            'w',
            driver='GTiff',
            height=image.shape[0],
            width=image.shape[1],
            count=image.shape[2],
            dtype=image.dtype,
            crs=LV95,
            gcp=points,
            transform=transform) as out:
        reshaped = rasterio.plot.reshape_as_raster(image)
        out.write(reshaped)




if __name__ == '__main__':
    os.makedirs("georeferenced", exist_ok=True)
    ref = Referencer()
    ref.process("HG3099")
