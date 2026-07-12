"""Feature extractor — z maski binarnej do wektora cech dla XGBoost.

Cechy zaprojektowane pod widok z góry:

    - geometria sylwetki: powierzchnia, obwód, długość/szerokość PCA, aspect
    - kształt konturu: solidity (wypukłość), extent, equivalent_diameter,
      eccentricity z momentów
    - 7 momentów Hu w skali log (niezmienniki obrót/skala/translacja)
    - profil szerokości w 8 koszykach wzdłuż osi głównej (znacznik proporcji
      barki vs zad — różnicuje kondycję świni)
    - ``camera_height_cm`` i ``px_per_cm`` jako jawny input modelu — dzięki
      temu jeden model XGBoost obsługuje różne wysokości kamery / kalibracje.

Wszystkie cechy są deterministyczne i taniе (~kilka ms na maskę 640x640 na
RPi 5).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional

import cv2
import numpy as np

WIDTH_PROFILE_BINS = 8
HEIGHT_PROFILE_BINS = 8
FEATURE_ORDER: list[str] = [
    "area_px",
    "perimeter_px",
    "length_px",
    "width_px",
    "aspect_ratio",
    "solidity",
    "extent",
    "equivalent_diameter_px",
    "eccentricity",
    "circularity",
    "compactness",
    "rectangularity",
    "convexity",
    "feret_max",
    "feret_min",
    "feret_ratio",
    "ellipse_major",
    "ellipse_minor",
    "ellipse_ratio",
    "hu_0", "hu_1", "hu_2", "hu_3", "hu_4", "hu_5", "hu_6",
    "wp_0", "wp_1", "wp_2", "wp_3", "wp_4", "wp_5", "wp_6", "wp_7",
    "wpn_0", "wpn_1", "wpn_2", "wpn_3", "wpn_4", "wpn_5", "wpn_6", "wpn_7",
    "area_cm2",
    "length_cm",
    "width_cm",
    "camera_height_cm",
    "px_per_cm",
    "depth_mean_mm",
    "depth_std_mm",
    "depth_min_mm",
    "depth_max_mm",
    "depth_median_mm",
    "height_mean_cm",
    "height_max_cm",
    "height_std_cm",
    "volume_proxy_cm3",
    "height_area_ratio",
    "hp_0", "hp_1", "hp_2", "hp_3", "hp_4", "hp_5", "hp_6", "hp_7",
    "hpn_0", "hpn_1", "hpn_2", "hpn_3", "hpn_4", "hpn_5", "hpn_6", "hpn_7",
    "cross_section_area_cm2",
]


@dataclass
class MaskFeatures:
    area_px: float = 0.0
    perimeter_px: float = 0.0
    length_px: float = 0.0
    width_px: float = 0.0
    aspect_ratio: float = 0.0
    solidity: float = 0.0
    extent: float = 0.0
    equivalent_diameter_px: float = 0.0
    eccentricity: float = 0.0
    circularity: float = 0.0
    compactness: float = 0.0
    rectangularity: float = 0.0
    convexity: float = 0.0
    feret_max: float = 0.0
    feret_min: float = 0.0
    feret_ratio: float = 0.0
    ellipse_major: float = 0.0
    ellipse_minor: float = 0.0
    ellipse_ratio: float = 0.0
    hu_moments: list[float] = field(default_factory=lambda: [0.0] * 7)
    width_profile: list[float] = field(default_factory=lambda: [0.0] * WIDTH_PROFILE_BINS)
    width_profile_norm: list[float] = field(default_factory=lambda: [0.0] * WIDTH_PROFILE_BINS)
    area_cm2: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    camera_height_cm: float = 0.0
    px_per_cm: float = 0.0
    depth_mean_mm: float = 0.0
    depth_std_mm: float = 0.0
    depth_min_mm: float = 0.0
    depth_max_mm: float = 0.0
    depth_median_mm: float = 0.0
    height_mean_cm: float = 0.0
    height_max_cm: float = 0.0
    height_std_cm: float = 0.0
    volume_proxy_cm3: float = 0.0
    height_area_ratio: float = 0.0
    height_profile: list[float] = field(default_factory=lambda: [0.0] * HEIGHT_PROFILE_BINS)
    height_profile_norm: list[float] = field(default_factory=lambda: [0.0] * HEIGHT_PROFILE_BINS)
    cross_section_area_cm2: float = 0.0

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.area_px,
            self.perimeter_px,
            self.length_px,
            self.width_px,
            self.aspect_ratio,
            self.solidity,
            self.extent,
            self.equivalent_diameter_px,
            self.eccentricity,
            self.circularity,
            self.compactness,
            self.rectangularity,
            self.convexity,
            self.feret_max,
            self.feret_min,
            self.feret_ratio,
            self.ellipse_major,
            self.ellipse_minor,
            self.ellipse_ratio,
            *self.hu_moments,
            *self.width_profile,
            *self.width_profile_norm,
            self.area_cm2,
            self.length_cm,
            self.width_cm,
            self.camera_height_cm,
            self.px_per_cm,
            self.depth_mean_mm,
            self.depth_std_mm,
            self.depth_min_mm,
            self.depth_max_mm,
            self.depth_median_mm,
            self.height_mean_cm,
            self.height_max_cm,
            self.height_std_cm,
            self.volume_proxy_cm3,
            self.height_area_ratio,
            *self.height_profile,
            *self.height_profile_norm,
            self.cross_section_area_cm2,
        ], dtype=np.float32)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("hu_moments")
        d.pop("width_profile")
        d.pop("width_profile_norm")
        d.pop("height_profile")
        d.pop("height_profile_norm")
        for i, v in enumerate(self.hu_moments):
            d[f"hu_{i}"] = v
        for i, v in enumerate(self.width_profile):
            d[f"wp_{i}"] = v
        for i, v in enumerate(self.width_profile_norm):
            d[f"wpn_{i}"] = v
        for i, v in enumerate(self.height_profile):
            d[f"hp_{i}"] = v
        for i, v in enumerate(self.height_profile_norm):
            d[f"hpn_{i}"] = v
        return d


def _min_feret_diameter(hull_points: np.ndarray) -> float:
    """Minimalny diameter Fereta (rotating calipers, uproszczone)."""
    if hull_points.shape[0] < 3:
        diffs = hull_points.max(axis=0) - hull_points.min(axis=0)
        return float(min(diffs[0], diffs[1])) if diffs.size >= 2 else 0.0
    rot_rect = cv2.minAreaRect(hull_points)
    return float(min(rot_rect[1]))


def _principal_axes(points: np.ndarray) -> tuple[float, float, float, float, float, float]:
    """Zwraca (mean_x, mean_y, lambda_max, lambda_min, cos_a, sin_a) z PCA 2D."""
    mean = points.mean(axis=0)
    centered = points - mean
    cov = np.cov(centered, rowvar=False, bias=True)
    cxx = float(cov[0, 0])
    cyy = float(cov[1, 1])
    cxy = float(cov[0, 1])
    tr = cxx + cyy
    det = cxx * cyy - cxy * cxy
    disc = max(0.0, tr * tr / 4 - det)
    sd = float(np.sqrt(disc))
    lambda_max = tr / 2 + sd
    lambda_min = max(0.0, tr / 2 - sd)
    if abs(cxy) > 1e-9:
        angle = float(np.arctan2(lambda_max - cxx, cxy))
    else:
        angle = 0.0 if cxx >= cyy else float(np.pi / 2)
    return float(mean[0]), float(mean[1]), lambda_max, lambda_min, float(np.cos(angle)), float(np.sin(angle))


def _width_profile(points: np.ndarray, mean_x: float, mean_y: float,
                   cos_a: float, sin_a: float, bins: int = WIDTH_PROFILE_BINS) -> list[float]:
    """Profil szerokości wzdłuż osi głównej — zwraca listę szerokości
    w pikselach (bezwzględnych, w przestrzeni maski).

    Dla każdego piksela liczymy projekcję na oś główną ``t`` i prostopadłą
    ``u``. Dzielimy zakres ``t`` na ``bins`` koszyków i dla każdego bierzemy
    rozpiętość ``u_max − u_min``.
    """
    if points.shape[0] == 0:
        return [0.0] * bins
    dx = points[:, 0] - mean_x
    dy = points[:, 1] - mean_y
    t = dx * cos_a + dy * sin_a
    u = -dx * sin_a + dy * cos_a
    t_min = float(t.min())
    t_max = float(t.max())
    if t_max - t_min < 1e-6:
        return [0.0] * bins
    edges = np.linspace(t_min, t_max, bins + 1)
    widths = [0.0] * bins
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if i == bins - 1:
            mask = (t >= lo) & (t <= hi)
        else:
            mask = (t >= lo) & (t < hi)
        if mask.sum() < 2:
            continue
        widths[i] = float(u[mask].max() - u[mask].min())
    return widths


def _height_profile(
    points: np.ndarray, depth_vals: np.ndarray,
    mean_x: float, mean_y: float,
    cos_a: float, sin_a: float,
    camera_height_cm: float,
    bins: int = HEIGHT_PROFILE_BINS,
) -> list[float]:
    """Height profile along the principal axis — mean height (cm) per bin."""
    if points.shape[0] == 0 or camera_height_cm <= 0:
        return [0.0] * bins
    dx = points[:, 0] - mean_x
    dy = points[:, 1] - mean_y
    t = dx * cos_a + dy * sin_a
    t_min, t_max = float(t.min()), float(t.max())
    if t_max - t_min < 1e-6:
        return [0.0] * bins
    heights_cm = camera_height_cm - depth_vals / 10.0
    heights_cm = np.clip(heights_cm, 0, camera_height_cm)
    edges = np.linspace(t_min, t_max, bins + 1)
    profile = [0.0] * bins
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (t >= lo) & (t <= hi) if i == bins - 1 else (t >= lo) & (t < hi)
        if sel.sum() < 2:
            continue
        profile[i] = float(heights_cm[sel].mean())
    return profile


def _extract_depth_features(
    mask: np.ndarray,
    depth_map: np.ndarray,
    camera_height_cm: float,
    px_per_cm: float,
    mean_x: float, mean_y: float,
    cos_a: float, sin_a: float,
) -> dict:
    """Extract depth-based features from the depth map within the mask region."""
    bin_mask = mask > 0
    depth_in_mask = depth_map[bin_mask].astype(np.float64)
    valid = depth_in_mask[depth_in_mask > 0]

    if len(valid) < 10:
        return {}

    depth_mean = float(valid.mean())
    depth_std = float(valid.std())
    depth_min = float(valid.min())
    depth_max = float(valid.max())
    depth_median = float(np.median(valid))

    heights_cm = camera_height_cm - valid / 10.0
    heights_cm = np.clip(heights_cm, 0, camera_height_cm)
    height_mean = float(heights_cm.mean())
    height_max = float(heights_cm.max())
    height_std = float(heights_cm.std())

    if px_per_cm > 0:
        pixel_area_cm2 = 1.0 / (px_per_cm * px_per_cm)
        volume_proxy = float(heights_cm.sum() * pixel_area_cm2)
        area_cm2 = float(len(valid) * pixel_area_cm2)
    else:
        volume_proxy = float(heights_cm.sum())
        area_cm2 = float(len(valid))

    height_area_ratio = height_mean / max(area_cm2, 1e-6)

    ys, xs = np.nonzero(bin_mask)
    depth_vals_all = depth_map[bin_mask].astype(np.float64)
    valid_idx = depth_vals_all > 0
    pts = np.column_stack([xs[valid_idx], ys[valid_idx]]).astype(np.float64)
    dv = depth_vals_all[valid_idx]

    hp = _height_profile(pts, dv, mean_x, mean_y, cos_a, sin_a, camera_height_cm)
    hp_max = max(hp) if hp else 1.0
    hp_norm = [v / hp_max if hp_max > 1e-6 else 0.0 for v in hp]

    cross_section = float(height_mean * (height_max - 0) * np.pi / 4) if height_max > 0 else 0.0

    return {
        "depth_mean_mm": depth_mean,
        "depth_std_mm": depth_std,
        "depth_min_mm": depth_min,
        "depth_max_mm": depth_max,
        "depth_median_mm": depth_median,
        "height_mean_cm": height_mean,
        "height_max_cm": height_max,
        "height_std_cm": height_std,
        "volume_proxy_cm3": volume_proxy,
        "height_area_ratio": height_area_ratio,
        "height_profile": hp,
        "height_profile_norm": hp_norm,
        "cross_section_area_cm2": cross_section,
    }


def extract_features(
    mask: np.ndarray,
    *,
    px_per_cm: float = 0.0,
    camera_height_cm: float = 0.0,
    depth_map: Optional[np.ndarray] = None,
) -> Optional[MaskFeatures]:
    """Wylicza wektor cech z binarnej maski (uint8 0/255 lub 0/1).

    Zwraca ``None`` gdy maska jest pusta lub kontur ma za mało punktów.
    """
    if mask.ndim != 2:
        raise ValueError("Maska musi być 2D")
    bin_mask = (mask > 0).astype(np.uint8)
    if bin_mask.sum() == 0:
        return None

    contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    if cnt.shape[0] < 5:
        return None

    area_px = float(cv2.contourArea(cnt))
    if area_px < 10:
        return None
    perimeter = float(cv2.arcLength(cnt, True))
    x, y, w, h = cv2.boundingRect(cnt)
    bbox_area = float(max(1, w * h))
    extent = area_px / bbox_area
    hull = cv2.convexHull(cnt)
    hull_area = float(max(1.0, cv2.contourArea(hull)))
    solidity = area_px / hull_area
    equivalent_diameter = float(np.sqrt(4 * area_px / np.pi))

    circularity = (4 * np.pi * area_px) / (perimeter * perimeter) if perimeter > 1e-6 else 0.0
    compactness = (perimeter * perimeter) / area_px if area_px > 1e-6 else 0.0

    rot_rect = cv2.minAreaRect(cnt)
    rr_w, rr_h = rot_rect[1]
    rr_area = float(max(1.0, rr_w * rr_h))
    rectangularity = area_px / rr_area

    hull_perimeter = float(cv2.arcLength(hull, True))
    convexity = hull_perimeter / perimeter if perimeter > 1e-6 else 0.0

    hull_points = cv2.convexHull(cnt, returnPoints=True).squeeze()
    if hull_points.ndim == 2 and hull_points.shape[0] >= 2:
        pts = hull_points.astype(np.float64)
        pair_dists = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2))
        feret_max = float(pair_dists.max())
        feret_min = float(_min_feret_diameter(hull_points))
    else:
        feret_max = float(max(w, h))
        feret_min = float(min(w, h))
    feret_ratio = feret_max / feret_min if feret_min > 1e-6 else 0.0

    if cnt.shape[0] >= 5:
        ellipse = cv2.fitEllipse(cnt)
        ell_major = float(max(ellipse[1]))
        ell_minor = float(min(ellipse[1]))
    else:
        ell_major = float(max(w, h))
        ell_minor = float(min(w, h))
    ell_ratio = ell_major / ell_minor if ell_minor > 1e-6 else 0.0

    moments = cv2.moments(bin_mask, binaryImage=True)
    if moments["m00"] <= 0:
        return None
    hu = cv2.HuMoments(moments).flatten()
    # log-scale, znak zachowany — typowy zabieg dla momentów Hu
    hu_log = [float(-np.sign(v) * np.log10(abs(v) + 1e-30)) for v in hu]

    # PCA na pikselach maski (a nie samym konturze) — stabilniejsze wymiary
    ys, xs = np.nonzero(bin_mask)
    points = np.column_stack([xs, ys]).astype(np.float64)
    mean_x, mean_y, lambda_max, lambda_min, cos_a, sin_a = _principal_axes(points)
    length_px = float(4 * np.sqrt(max(0.0, lambda_max)))
    width_px = float(4 * np.sqrt(max(0.0, lambda_min)))
    aspect = length_px / width_px if width_px > 1e-6 else 0.0

    if (lambda_max + lambda_min) > 1e-9:
        eccentricity = float(np.sqrt(1.0 - lambda_min / lambda_max)) if lambda_max > 1e-9 else 0.0
    else:
        eccentricity = 0.0

    profile = _width_profile(points, mean_x, mean_y, cos_a, sin_a, WIDTH_PROFILE_BINS)
    max_wp = max(profile) if profile else 1.0
    profile_norm = [v / max_wp if max_wp > 1e-6 else 0.0 for v in profile]

    if px_per_cm and px_per_cm > 0:
        s = float(px_per_cm)
        area_cm2 = area_px / (s * s)
        length_cm = length_px / s
        width_cm = width_px / s
    else:
        area_cm2 = 0.0
        length_cm = 0.0
        width_cm = 0.0

    depth_feats: dict = {}
    if depth_map is not None and camera_height_cm > 0:
        depth_feats = _extract_depth_features(
            bin_mask, depth_map, camera_height_cm, px_per_cm,
            mean_x, mean_y, cos_a, sin_a,
        )

    return MaskFeatures(
        area_px=area_px,
        perimeter_px=perimeter,
        length_px=length_px,
        width_px=width_px,
        aspect_ratio=aspect,
        solidity=solidity,
        extent=extent,
        equivalent_diameter_px=equivalent_diameter,
        eccentricity=eccentricity,
        circularity=float(circularity),
        compactness=float(compactness),
        rectangularity=float(rectangularity),
        convexity=float(convexity),
        feret_max=float(feret_max),
        feret_min=float(feret_min),
        feret_ratio=float(feret_ratio),
        ellipse_major=float(ell_major),
        ellipse_minor=float(ell_minor),
        ellipse_ratio=float(ell_ratio),
        hu_moments=hu_log,
        width_profile=profile,
        width_profile_norm=profile_norm,
        area_cm2=area_cm2,
        length_cm=length_cm,
        width_cm=width_cm,
        camera_height_cm=float(camera_height_cm),
        px_per_cm=float(px_per_cm),
        depth_mean_mm=depth_feats.get("depth_mean_mm", 0.0),
        depth_std_mm=depth_feats.get("depth_std_mm", 0.0),
        depth_min_mm=depth_feats.get("depth_min_mm", 0.0),
        depth_max_mm=depth_feats.get("depth_max_mm", 0.0),
        depth_median_mm=depth_feats.get("depth_median_mm", 0.0),
        height_mean_cm=depth_feats.get("height_mean_cm", 0.0),
        height_max_cm=depth_feats.get("height_max_cm", 0.0),
        height_std_cm=depth_feats.get("height_std_cm", 0.0),
        volume_proxy_cm3=depth_feats.get("volume_proxy_cm3", 0.0),
        height_area_ratio=depth_feats.get("height_area_ratio", 0.0),
        height_profile=depth_feats.get("height_profile", [0.0] * HEIGHT_PROFILE_BINS),
        height_profile_norm=depth_feats.get("height_profile_norm", [0.0] * HEIGHT_PROFILE_BINS),
        cross_section_area_cm2=depth_feats.get("cross_section_area_cm2", 0.0),
    )
