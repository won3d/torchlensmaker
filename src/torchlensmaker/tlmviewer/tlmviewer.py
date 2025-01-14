from IPython.display import display, HTML
import string
import uuid
import os.path
import json
import torch

Tensor = torch.Tensor

import torchlensmaker as tlm


def get_script_template() -> str:
    "Get the js script template string"

    dir_path = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(dir_path, "script_template.js"), encoding="utf-8") as f:
        return "<script type='module'>" + f.read() + "</script>"


def get_div_template() -> str:
    return "<div data-jp-suppress-context-menu id='$div_id' style='width: 800px; height: 600px;'></div>"


def random_id() -> str:
    return f"tlmviewer-{uuid.uuid4().hex[:8]}"


def show(data: object, ndigits=None, dump=False) -> None:
    div_id = random_id()
    div_template = get_div_template()
    script_template = get_script_template()

    json_data = json.dumps(data, allow_nan=False)

    if ndigits is not None:
        json_data = json.dumps(json.loads(json_data, parse_float=lambda x: round(float(x), ndigits)))

    if dump:
        print(json_data)

    div = string.Template(div_template).substitute(div_id=div_id)
    script = string.Template(script_template).substitute(data=json_data, div_id=div_id)
    display(HTML(div + script))  # type: ignore


def render_surface(surface: tlm.surfaces.ImplicitSurface, matrix4: Tensor) -> object:
    N = 100
    samples = surface.samples2D(N)

    obj = {"matrix": matrix4.tolist(), "samples": samples.tolist()}

    # outline
    if isinstance(surface.outline, tlm.SquareOutline):
        obj["side_length"] = surface.outline.side_length

    return obj


def render_rays(rays: Tensor, length: float, color: str = "#ffa724") -> list[object]:
    rays_start = rays[:, :3]
    rays_end = rays_start + length * rays[:, 3:]
    data = torch.hstack((rays_start, rays_end)).tolist()
    return {
        "type": "rays",
        "data": data,
        "color": color,
    }


def render(
    rays: Tensor | None = None,
    points: Tensor | None = None,
    normals: Tensor | None = None,
    surfaces: list[tlm.surfaces.ImplicitSurface] | None = None,
    transforms: list[tlm.Surface3DTransform] | None = None,
    rays_length: float | None = None,
    rays_color: str = "#ffa724",
) -> object:
    "Render tlm objects to json-able object"

    groups = []

    if surfaces is not None:
        groups.append(
            {
                "type": "surfaces",
                "data": [
                    render_surface(s, t.matrix4(s))
                    for s, t in zip(surfaces, transforms)
                ],
            }
        )

    if rays is not None:
        groups.append(render_rays(rays, rays_length))

    if points is not None:
        groups.append(
            {
                "type": "points",
                "data": points.tolist(),
                "color": "#ff0000",
            }
        )

    if normals is not None:
        groups.append(
            {
                "type": "arrows",
                "data": [
                    n.tolist() + p.tolist() + [1.0] for p, n in zip(points, normals)
                ],
            }
        )

    return {"data": groups}
