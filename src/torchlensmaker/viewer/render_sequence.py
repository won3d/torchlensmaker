import torch
import torch.nn as nn
import torchlensmaker as tlm

from typing import Literal, Any, Optional, Type, Dict, TypeVar

from torchlensmaker.tensorframe import TensorFrame


Tensor = torch.Tensor

# Color theme
color_valid = "#ffa724"
color_blocked = "red"
color_focal_point = "red"


def render_rays_until(P: Tensor, V: Tensor, end: Tensor, color: str) -> list[Any]:
    "Render rays until an absolute X coordinate"

    t = (end - P[:, 0]) / V[:, 0]
    ends = P + t.unsqueeze(1).expand_as(V) * V
    return [tlm.viewer.render_rays(P, ends, color=color)]


def render_rays_length(P: Tensor, V: Tensor, length: float, color: str) -> list[Any]:
    "Render rays with fixed length"

    return [tlm.viewer.render_rays(P, P + length * V, color=color)]


class SurfaceArtist:
    @staticmethod
    def render_element(element: nn.Module, inputs: Any, _outputs: Any) -> list[Any]:

        dim, dtype = inputs.transforms[0].dim, inputs.transforms[0].dtype
        chain = inputs.transforms + element.surface_transform(dim, dtype)
        transform = tlm.forward_kinematic(chain)

        # TODO find a way to group surfaces together?
        return [
            tlm.viewer.render_surfaces(
                [element.surface], [transform], dim=transform.dim, N=100
            )
        ]

    @staticmethod
    def render_rays(element: nn.Module, inputs: Any, outputs: Any) -> list[Any]:

        # If rays are not blocked, render simply all rays from collision to collision
        if outputs.blocked is None:
            return [tlm.viewer.render_rays(inputs.P, outputs.P, color=color_valid)]

        # Else, split into colliding and non colliding rays using blocked mask
        else:
            valid = ~outputs.blocked
            group_valid = (
                [tlm.viewer.render_rays(inputs.P[valid], outputs.P, color=color_valid)]
                if inputs.P[valid].numel() > 0
                else []
            )

            P, V = inputs.P[outputs.blocked], inputs.V[outputs.blocked]
            if P.numel() > 0:
                dim, dtype = inputs.transforms[0].dim, inputs.transforms[0].dtype
                chain = inputs.transforms + element.surface_transform(dim, dtype)
                transform = tlm.forward_kinematic(chain)
                target = transform.direct_points(torch.zeros(1, dim, dtype=dtype))[0]

                group_blocked = render_rays_until(P, V, target[0], color=color_blocked)

            else:
                group_blocked = []

            return group_valid + group_blocked
            # Render non blocked rays


class FocalPointArtist:
    @staticmethod
    def render_element(
        element: nn.Module, inputs: tlm.OpticalData, _outputs: tlm.OpticalData
    ) -> list[Any]:

        target = inputs.target().unsqueeze(0)
        return [tlm.viewer.render_points(target, color_focal_point)]

    @staticmethod
    def render_rays(element: nn.Module, inputs: Any, outputs: Any) -> list[Any]:
        target = inputs.target()
        mean_ray = inputs.P[:, 0].mean()
        # Focal point is ahed of the rays
        if target[0] > mean_ray:
            return render_rays_until(inputs.P, inputs.V, target[0], color_valid)
        # Focal point is behind the rays
        else:
            dist = mean_ray - target[0]
            return render_rays_until(inputs.P, inputs.V, mean_ray + dist, color_valid)


class ApertureArtist:
    @staticmethod
    def render_element(
        element: nn.Module, inputs: tlm.OpticalData, _outputs: tlm.OpticalData
    ) -> list[Any]:

        target = inputs.target().unsqueeze(0)
        return [tlm.viewer.render_points(target, color_focal_point)]

    @staticmethod
    def render_rays(element: nn.Module, inputs: Any, outputs: Any) -> list[Any]:
        return SurfaceArtist.render_rays(element, inputs, outputs)


class JointArtist:
    @staticmethod
    def render_element(element: nn.Module, inputs: Any, _outputs: Any) -> list[Any]:

        dim, dtype = inputs.transforms[0].dim, inputs.transforms[0].dtype
        transform = tlm.forward_kinematic(inputs.transforms)
        joint = transform.direct_points(torch.zeros((dim,), dtype=dtype))

        return [{"type": "points", "data": [joint.tolist()]}]


artists_dict: Dict[type, type] = {
    tlm.OpticalSurface: SurfaceArtist,
    tlm.FocalPoint: FocalPointArtist,
    # tlm.Aperture: ApertureArtist,
}


def inspect_stack(execute_list: list[tuple[nn.Module, Any, Any]]) -> None:
    for module, inputs, outputs in execute_list:
        print(type(module))
        print("inputs.transform:")
        for t in inputs.transforms:
            print(t)
        print()
        print("outputs.transform:")
        for t in outputs.transforms:
            print(t)
        print()


def render_sequence(
    optics: nn.Module,
    sampling: dict[str, Any],
    end: Optional[float] = None,
) -> Any:
    dim, dtype = sampling["dim"], sampling["dtype"]
    execute_list, top_output = tlm.full_forward(optics, tlm.default_input(sampling))

    scene = tlm.viewer.new_scene("2D" if dim == 2 else "3D")

    # Render elements
    for module, inputs, outputs in execute_list:

        # render chain join position for every module
        scene["data"].extend(JointArtist.render_element(module, inputs, outputs))

        # find matching artists for this module, use the first one for rendering
        artists = [a for typ, a in artists_dict.items() if isinstance(module, typ)]

        if len(artists) > 0:
            artist = artists[0]
            scene["data"].extend(artist.render_element(module, inputs, outputs))

            if inputs.P.numel() > 0:
                scene["data"].extend(artist.render_rays(module, inputs, outputs))

    # Render output rays
    if end is not None:
        scene["data"].extend(
            render_rays_length(top_output.P, top_output.V, end, color=color_valid)
        )

    return scene


def default_show_sampling(
    optics: nn.Module, mode: Literal["2D", "3D"]
) -> dict[str, Any]:
    "Guess good default sampling parameters for the purposes of viewing"

    if mode == "2D":
        return {"dim": 2, "dtype": torch.float64, "base": 10}
    else:
        return {"dim": 3, "dtype": torch.float64, "base": 10}


def ipython_show(
    optics: nn.Module,
    mode: Literal["2D", "3D"],
    end: Optional[float] = None,
    dump: bool = False,
) -> None:

    sampling = default_show_sampling(optics, mode)

    scene = tlm.viewer.render_sequence(optics, sampling, end)

    if dump:
        tlm.viewer.dump(scene, ndigits=2)

    tlm.viewer.ipython_display(scene)
