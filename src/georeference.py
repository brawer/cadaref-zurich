# mutation: HG3099
# parcel: HG7698
# topleft:  2678576.67, 1251928.47
# botright: 2678672.85, 1251798.69

import csv
import json
import math
import os
from collections import namedtuple

import cv2
import numpy
import PIL.Image
import quads
import rasterio
import rasterio.plot
import rasterio.transform
from rasterio.control import GroundControlPoint

from classify import classify_contour

# Ground Control Points: Border points
HGD4867 = ("HGD4867", 2678627.89, 1251882.92)  # white circle
HGE4867 = ("HGE4867", 2678644.58, 1251853.03)  # white circle
HGG4866 = ("HGG4866", 2678612.35, 1251849.40)  # white circle
HGN4862 = ("HGN4862", 2678624.15, 1251853.03)  # black dot

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
                "w",
                driver="GTiff",
                height=rendered_img.shape[0],
                width=rendered_img.shape[1],
                count=rendered_img.shape[2],
                dtype=rendered_img.dtype,
                crs=LV95,
                transform=transform,
            ) as out:
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
        best_model = None
        best_residual = math.inf
        img = numpy.asarray(thresholded).astype(numpy.uint8) * 255
        map_points = self._find_map_points(img)
        # TODO: Remove filtering, this is just for debugging.
        map_points = [p for p in map_points if p[2] == "double_white_circle"]
        if len(map_points) < 3:
            return None

        scale_x, scale_y = self._get_dpi_scale(thresholded, rendered)
        dpi = float(thresholded.info["dpi"][0])
        for map_scale in (500, 1000, 250):  # TODO: 1000, 250, 200 -- from OCR?
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
            # geo_points = [p.data for p in geo_points if p.data.style == "double_white_circle"]
            if len(geo_points) < 3:
                continue

            # print("-------", map_scale, scale_x, scale_y)
            # print(len(geo_points), len(map_points), pixels_to_meters)
            tolerance = 1.0  # meters
            for pp in range(len(map_points) - 1):
                p = map_points[pp]
                # print("P:", p)
                for qq in range(pp + 1, len(map_points)):
                    q = map_points[qq]
                    dx = (p[0] - q[0]) * pixels_to_meters
                    dy = (p[1] - q[1]) * pixels_to_meters
                    dist_pq_sq = dx * dx + dy * dy
                    dist_pq = math.sqrt(dist_pq_sq)
                    min_dist_ab_sq = (dist_pq - tolerance) ** 2
                    max_dist_ab_sq = (dist_pq + tolerance) ** 2
                    for aa in range(len(geo_points)):
                        a = geo_points[aa].data
                        # if a.id != "HG2805": continue
                        if p[2] != a.style:
                            continue
                        # if a.id != 'HG2805': continue  # ----------- TODO: remove
                        for bb in range(aa + 1, len(geo_points)):
                            b = geo_points[bb].data
                            # if b.id != "HG2775": continue
                            if q[2] != b.style:
                                continue
                            dist_ab_sq = dist_sq(a, b)
                            if not (min_dist_ab_sq <= dist_ab_sq <= max_dist_ab_sq):
                                continue
                            # print("*** GIRAFFE A=%s B=%s P=(%d,%d) Q=(%d,%d) ΔAB=%.1f ΔPQ=%.1f" % (a.id, b.id, int(p[0]), int(p[1]), int(q[0]), int(q[1]), math.sqrt(dist_ab_sq), dist_pq))
                            for cc in range(len(geo_points)):
                                if cc == aa or cc == bb:
                                    continue
                                c = geo_points[cc].data
                                # if c.id != "HG2804":
                                #    continue
                                dist_ac = math.sqrt(dist_sq(a, c))
                                dist_bc = math.sqrt(dist_sq(b, c))
                                min_dist_pr_sq = (dist_ac - tolerance) ** 2
                                max_dist_pr_sq = (dist_ac + tolerance) ** 2
                                min_dist_qr_sq = (dist_bc - tolerance) ** 2
                                max_dist_qr_sq = (dist_bc + tolerance) ** 2
                                # print("    Looking for ΔPR between %.1f and %.1f meters" % (math.sqrt(min_dist_pr_sq), math.sqrt(max_dist_pr_sq)))
                                # print("    Looking for ΔQR between %.1f and %.1f meters" % (math.sqrt(min_dist_qr_sq), math.sqrt(max_dist_qr_sq)))
                                for rr in range(qq + 1, len(map_points)):
                                    if rr == pp or rr == qq:
                                        continue
                                    r = map_points[rr]
                                    if r[2] != c.style:
                                        continue
                                    dx = (p[0] - r[0]) * pixels_to_meters
                                    dy = (p[1] - r[1]) * pixels_to_meters
                                    dist_pr_sq = dx * dx + dy * dy
                                    if not (
                                        min_dist_pr_sq <= dist_pr_sq <= max_dist_pr_sq
                                    ):
                                        continue
                                    dx = (q[0] - r[0]) * pixels_to_meters
                                    dy = (q[1] - r[1]) * pixels_to_meters
                                    dist_qr_sq = dx * dx + dy * dy
                                    if not (
                                        min_dist_qr_sq <= dist_qr_sq <= max_dist_qr_sq
                                    ):
                                        continue
                                    if False:
                                        print(
                                            "*** ZEBRA A=%s B=%s C=%s P=(%d,%d) Q=(%d,%d) R=(%d,%d)"
                                            % (
                                                a.id,
                                                b.id,
                                                c.id,
                                                p[0],
                                                p[1],
                                                q[0],
                                                q[1],
                                                r[0],
                                                r[1],
                                            )
                                        )
                                    if False:
                                        print(
                                            "        ΔPQ=%.1f vs. ΔAB=%.1f"
                                            % (
                                                math.sqrt(dist_pq_sq),
                                                math.sqrt(dist_ab_sq),
                                            )
                                        )
                                        print(
                                            "        ΔPR=%.1f vs. ΔAC=%.1f"
                                            % (math.sqrt(dist_pr_sq), dist_ac)
                                        )
                                        print(
                                            "        ΔQR=%.1f vs. ΔBC=%.1f"
                                            % (math.sqrt(dist_qr_sq), dist_bc)
                                        )
                                    gcp_p = GroundControlPoint(
                                        col=p[0],
                                        row=p[1],
                                        x=a.x,
                                        y=a.y,
                                        id=a.id,
                                    )
                                    gcp_q = GroundControlPoint(
                                        col=q[0],
                                        row=q[1],
                                        x=b.x,
                                        y=b.y,
                                        id=b.id,
                                    )
                                    gcp_r = GroundControlPoint(
                                        col=r[0],
                                        row=r[1],
                                        x=c.x,
                                        y=c.y,
                                        id=c.id,
                                    )
                                    transform = rasterio.transform.from_gcps(
                                        [gcp_p, gcp_q, gcp_r]
                                    )
                                    residual = self.eval_model(
                                        transform, map_points, geo_points
                                    )
                                    if residual < best_residual:
                                        print("*** found new best", residual)
                                        best_residual = residual
                                        gcp_p_scaled = GroundControlPoint(
                                            col=int(p[0] * scale_x + 0.5),
                                            row=int(p[1] * scale_y + 0.5),
                                            x=a.x,
                                            y=a.y,
                                            id=a.id,
                                        )
                                        gcp_q_scaled = GroundControlPoint(
                                            col=int(q[0] * scale_x + 0.5),
                                            row=int(q[1] * scale_y + 0.5),
                                            x=b.x,
                                            y=b.y,
                                            id=b.id,
                                        )
                                        gcp_r_scaled = GroundControlPoint(
                                            col=int(r[0] * scale_x + 0.5),
                                            row=int(r[1] * scale_y + 0.5),
                                            x=c.x,
                                            y=c.y,
                                            id=c.id,
                                        )
                                        best_model = rasterio.transform.from_gcps(
                                            [gcp_p_scaled, gcp_q_scaled, gcp_r_scaled]
                                        )
                                        # TODO: Just for debugging
                                        if residual < 300.5532:
                                            return best_model
        return best_model

    # Compute a quality metric for a candidate model. Lower is better.
    def eval_model(self, transform, map_points, geo_points):
        transformer = rasterio.transform.AffineTransformer(transform)
        residual = 0.0
        for p in map_points:
            col, row, style = p[0], p[1], p[2]
            xy = transformer.xy(row, col)
            p_x, p_y = float(xy[0]), float(xy[1])
            # print("*** ECHIDNA", col, row, p_x, p_y)
            p_dist_sq = 100.0  # penalty if no point is found
            for q in self.points.nearest_neighbors((p_x, p_y), count=5):
                q = q.data
                if q.style != style:
                    continue
                dx, dy = p_x - q.x, p_y - q.y
                p_dist_sq = dx * dx + dy * dy
                break
            residual += p_dist_sq
            # print(p, (p_x,p_y), q)
            # print("delta:", dx, dy, math.sqrt(dist_sq))
            # break
        # print("*** ECHCHIDNA residual=%f" % residual)
        return residual

    def _guess_page_center(self, meta):
        min_x, max_x, min_y, max_y = 1e9, 0.0, 1e9, 0.0
        for parcel_id in meta["parcels"]:
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
        with open("parcels.csv", "r") as csvfile:
            for row in csv.DictReader(csvfile):
                id = row["parcel"]
                x0, x1 = float(row["min_x"]), float(row["max_x"])
                y0, y1 = float(row["min_y"]), float(row["max_y"])
                self.parcels[id] = (x0, x1, y0, y1)

    def _read_points(self):
        points = []
        with open("border_points.csv", "r") as csvfile:
            for row in csv.DictReader(csvfile):
                point_type = row["type"]
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
        with open("fix_points.csv", "r") as csvfile:
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


def dist_sq(a, b):
    delta_x = a.x - b.x
    delta_y = a.y - b.y
    return delta_x * delta_x + delta_y * delta_y


if __name__ == "__main__":
    PIL.Image.MAX_IMAGE_PIXELS = None
    os.makedirs("georeferenced", exist_ok=True)
    ref = Referencer()
    for f in sorted(os.listdir("thresholded")):
        if not f.startswith("HG3099"):
            continue
        if True or not os.path.exists(os.path.join("georeferenced", f)):
            mutation = f.removesuffix(".tif")
            print(mutation)
            ref.process(mutation)
