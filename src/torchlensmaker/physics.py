import torch
from typing import Literal

Tensor = torch.Tensor
RefractionCriticalAngleMode = Literal["drop", "nan", "clamp", "reflect"]


def reflection(rays: Tensor, normals: Tensor) -> Tensor:
    """
    Vector based reflection.

    Args:
        ray: unit vectors of the incident rays, shape (B, 2)
        normal: unit vectors normal to the surface, shape (B, 2)

    Returns:
        vectors of the reflected vector with shape (B, 2)
    """

    dot_product = torch.sum(rays * normals, dim=1, keepdim=True)
    R = rays - 2 * dot_product * normals
    return torch.div(R, torch.norm(R, dim=1, keepdim=True))


def refraction(
    rays: Tensor,
    normals: Tensor,
    n1: float | Tensor,
    n2: float | Tensor,
    critical_angle: RefractionCriticalAngleMode = "drop",
) -> Tensor:
    """
    Vector based refraction (Snell's law).

    The 'critical_angle' argument specifies how incident rays beyond the
    critical angle are handled:

        * 'nan': Incident rays beyond the critical angle will refract
          as nan values. The returned tensor always has the same shape as the
          input tensors.

        * 'clamp': Incident rays beyond the critical angle all refract at 90°.
          The returned tensor always has the same shape as the input tensors.

        * 'drop' (default): Incident rays beyond the critical angle will not be
          refracted. The returned tensor doesn't necesarily have the same shape
          as the input tensors.

        * 'reflect': Incident rays beyond the critical angle are reflected. This
          is true physical behavior aka total internal reflection. The returned
          tensor always has the same shape as the input tensors.

    Args:
        rays: unit vectors of the incident rays, shape (B, 2/3)
        normals: unit vectors normal to the surface, shape (B, 2/3)
        n1: index of refraction of the incident medium, float or tensor of shape (N)
        n2: index of refraction of the refracted medium float or tensor of shape (N)
        critical_angle: one of 'nan', 'clamp', 'drop', 'reflect' (default: 'nan')

    Returns:
        unit vectors of the refracted rays, shape (C, 2)
    """

    assert rays.dim() == 2 and rays.shape[1] in {2, 3}
    assert normals.dim() == 2 and normals.shape[1] in {2, 3}
    assert rays.shape[0] == normals.shape[0]

    # Compute dot product for the batch, aka cosine of the incident angle
    cos_theta_i = torch.sum(rays * -normals, dim=1, keepdim=True)

    # Convert n1 and n2 into tensors
    N = rays.shape[0]
    n1 = torch.as_tensor(n1).expand((N,))
    n2 = torch.as_tensor(n2).expand((N,))

    # Compute R_perp
    eta = n1 / n2
    R_perp = eta.unsqueeze(1) * (rays + cos_theta_i * normals)

    # Compute R_para, depending on critical angle option
    if critical_angle == "nan":
        R_para = (
            -torch.sqrt(1 - torch.sum(R_perp * R_perp, dim=1, keepdim=True)) * normals
        )

    elif critical_angle == "clamp":
        radicand = torch.clamp(
            1 - torch.sum(R_perp * R_perp, dim=1, keepdim=True), min=0.0, max=None
        )
        R_para = -torch.sqrt(radicand) * normals

    elif critical_angle == "drop":
        radicand = 1 - torch.sum(R_perp * R_perp, dim=1, keepdim=True)
        valid = (radicand >= 0.0).squeeze(1)
        R_para = -torch.sqrt(radicand[valid, :]) * normals[valid, :]
        R_perp = R_perp[valid, :]

    elif critical_angle == "reflect":
        radicand = 1 - torch.sum(R_perp * R_perp, dim=1, keepdim=True)
        valid = (radicand >= 0.0).squeeze(1)
        R_para = (
            -torch.sqrt(1 - torch.sum(R_perp * R_perp, dim=1, keepdim=True)) * normals
        )
        R = R_perp + R_para

        R[~valid] = reflection(rays, normals)[~valid]
        return torch.div(R, torch.norm(R, dim=1, keepdim=True))

    else:
        raise ValueError(
            f"critical_angle must be one of 'nan', 'clamp', 'drop'. Got {repr(critical_angle)}."
        )

    # Combine R_perp and R_para and normalize the result
    R = R_perp + R_para
    return torch.div(R, torch.norm(R, dim=1, keepdim=True))
