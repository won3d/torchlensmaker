import math

import torch
import torch.nn as nn

from torchlensmaker.shapes.common import intersect_newton
from torchlensmaker.shapes import BaseShape


class CircularArc(BaseShape):
    """
    An arc of circle

    Parameters:
        width: typically radius of the lens
        arc_radius: radius of curvature of the surface profile

        The sign of the radius indicates the direction of the center of curvature.

        The internal parameter is curvature = 1/radius, to allow optimization to
        cross over zero and change sign.
    """

    def __init__(self, width, arc_radius):
        assert torch.abs(torch.as_tensor(arc_radius)) >= width

        if isinstance(arc_radius, nn.Parameter):
            self._K = nn.Parameter(torch.tensor(1./arc_radius.item()))
        else:
            self._K = torch.as_tensor(1./arc_radius)
        
        self.width = width

    def parameters(self):
        if isinstance(self._K, nn.Parameter):
            return {"K": self._K}
        else:
            return {}

    def coefficients(self):
        K = self._K
        
        # Special case to avoid div by zero
        if torch.abs(K) < 1e-8:
            return torch.sign(K) * 1e8
        else:
            return 1. / K

    def domain(self):
        R = self.coefficients()
        a = math.acos(self.width / torch.abs(R))
        if R > 0:
            return a, math.pi - a
        else:
            return -math.pi + a, -a

    def evaluate(self, ts):
        ts = torch.as_tensor(ts)
        R = self.coefficients()
        X = torch.abs(R)*torch.cos(ts)
        Y = torch.abs(R)*torch.sin(ts) - R
        return torch.stack((X, Y), dim=-1)

    def derivative(self, ts):
        R = self.coefficients()
        return torch.stack([
            - torch.abs(R) * torch.sin(ts),
            torch.abs(R) * torch.cos(ts)
        ], dim=-1)

    def normal(self, ts):
        "Normal vectors at the given parametric locations"

        deriv = self.derivative(ts)
        normal = torch.stack((-deriv[:, 1], deriv[:, 0]), dim=-1)
        return normal / torch.linalg.vector_norm(normal, dim=1).view((-1, 1))

    def newton_init(self, size):
        return torch.full(size, math.pi/2)
    
    def collide(self, lines):
        tn = intersect_newton(self, lines)
        return self.evaluate(tn), self.normal(tn)
