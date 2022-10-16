import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .. import keypoints
from . import prediction_utils


class KeypointsNetwork(nn.Module):
    """
    Keypoints to neural PCs / neural activity model
    """

    def __init__(
        self, n_in=28, n_kp=None, n_filt=10, kernel_size=201,
        n_core_layers=2, n_latents=256, n_out_layers=1,
        n_out=128, n_med=50, n_animals=1,
        identity=False, relu_wavelets=True, relu_latents=True,
    ):
        super().__init__()
        self.core = Core(
            n_in=n_in, n_kp=n_kp, n_filt=n_filt, kernel_size=kernel_size,
            n_layers=n_core_layers, n_med=n_med, n_latents=n_latents,
            identity=identity, 
            relu_wavelets=relu_wavelets, relu_latents=relu_latents,
        )
        self.readout = Readout(
            n_animals=n_animals, n_latents=n_latents, n_layers=n_out_layers, n_out=n_out
        )

    def forward(self, x, sample_inds=None, animal_id=0):
        latents = self.core(x)
        if sample_inds is not None:
            latents = latents[sample_inds]
        latents = latents.reshape(x.shape[0], -1, latents.shape[-1])
        y_pred = self.readout(latents, animal_id=animal_id)
        return y_pred, latents

    def train_model(
        self,
        X_dat,
        Y_dat,
        tcam_list,
        tneural_list,
        delay=-1,
        smoothing_penalty=0.5,
        n_iter=300,
        learning_rate=1e-3,
        annealing_steps=2,
        weight_decay=1e-4,
        device=torch.device("cuda"),
        verbose=False,
    ):
        """
        Train KeypointsNetwork (behavior -> neural) model using multiple animals
        Parameters
        ----------
        X_dat: list of 2D arrays
            behavior data for each animal
        Y_dat: list of 2D arrays
            neural data for each animal
        tcam_list: list of 1D arrays
            timestamps for behavior data for each animal
        tneural_list: list of 1D arrays
            timestamps for neural data for each animal
        """
        
        optimizer = torch.optim.AdamW(
            self.parameters(), lr=learning_rate, weight_decay=weight_decay
        )
        ### make input data a list if it's not already
        not_list = False
        if not isinstance(X_dat, list):
            not_list = True
            X_dat, Y_dat, tcam_list, tneural_list = (
                [X_dat],
                [Y_dat],
                [tcam_list],
                [tneural_list],
            )

        ### split data into train / test and concatenate
        arrs = [[], [], [], [], [], [], [], [], [], []]
        for i, (X, Y, tcam, tneural) in enumerate(
            zip(X_dat, Y_dat, tcam_list, tneural_list)
        ):
            dsplits = prediction_utils.split_data(
                X, Y, tcam, tneural, delay=delay, device=device
            )
            for d, a in zip(dsplits, arrs):
                a.append(d)
        (
            X_train,
            X_test,
            Y_train,
            Y_test,
            itrain_sample_b,
            itest_sample_b,
            itrain_sample,
            itest_sample,
            itrain,
            itest,
        ) = arrs
        n_animals = len(X_train)

        tic = time.time()
        ### determine total number of batches across all animals to sample from
        n_batches = [0]
        n_batches.extend([X_train[i].shape[0] for i in range(n_animals)])
        n_batches = np.array(n_batches)
        c_batches = np.cumsum(n_batches)
        n_batches = n_batches.sum()

        anneal_epochs = n_iter - 50 * np.arange(1, annealing_steps + 1)

        ### optimize all parameters with SGD
        for epoch in range(n_iter):
            self.train()
            if epoch in anneal_epochs:
                if verbose:
                    print("annealing learning rate")
                optimizer.param_groups[0]["lr"] /= 10.0
            np.random.seed(epoch)
            rperm = np.random.permutation(n_batches)
            train_loss = 0
            for nr in rperm:
                i = np.nonzero(nr >= c_batches)[0][-1]
                n = nr - c_batches[i]

                y_pred = self.forward(
                    X_train[i][n].unsqueeze(0), itrain_sample_b[i][n], animal_id=i
                )[0]
                loss = ((y_pred - Y_train[i][n].unsqueeze(0)) ** 2).mean()
                loss += (
                    smoothing_penalty
                    * (torch.diff(self.core.features[1].weight) ** 2).sum()
                )
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            train_loss /= n_batches

            # compute test loss and test variance explained
            if epoch % 20 == 0 or epoch == n_iter - 1:
                ve_all, y_pred_all = [], []
                self.eval()
                with torch.no_grad():
                    pstr = f"epoch {epoch}, "
                    for i in range(n_animals):
                        y_pred = self(X_test[i], itest_sample_b[i].flatten(), animal_id=i)[
                            0
                        ]
                        y_pred = y_pred.reshape(-1, y_pred.shape[-1])
                        tl = ((y_pred - Y_test[i]) ** 2).mean()
                        ve = 1 - tl / ((Y_test[i] - Y_test[i].mean(axis=0)) ** 2).mean()
                        y_pred_all.append(y_pred.cpu().numpy())
                        ve_all.append(ve.item())
                        if n_animals == 1:
                            pstr += f"animal {i}, train loss {train_loss:.4f}, test loss {tl.item():.4f}, varexp {ve.item():.4f}, "
                        else:
                            pstr += f"varexp{i} {ve.item():.4f}, "
                pstr += f"time {time.time()-tic:.1f}s"
                if verbose:
                    print(pstr)

        if not_list:
            return y_pred_all[0], ve_all[0], itest[0]
        else:
            return y_pred_all, ve_all, itest



class Core(nn.Module):
    """
    Core network of the KeypointsNetwork with the following structure:
        linear -> conv1d -> relu -> linear -> relu = latents for KeypointsNetwork model
    """

    def __init__(
        self, n_in=28, n_kp=None, n_filt=10, kernel_size=201,
        n_layers=1, n_med=50, n_latents=256, identity=False,
        relu_wavelets=True, relu_latents=True,
    ):
        super().__init__()
        self.n_in = n_in
        self.n_kp = n_in if n_kp is None or identity else n_kp
        self.n_filt = (n_filt // 2) * 2  # must be even for initialization
        self.relu_latents = relu_latents
        self.relu_wavelets = relu_wavelets
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.n_latents = n_latents
        self.features = nn.Sequential()

        # combine keypoints into n_kp features
        if identity:
            self.features.add_module("linear0", nn.Identity(self.n_in))
        else:
            self.features.add_module(
                "linear0",
                nn.Sequential(
                    nn.Linear(self.n_in, self.n_kp),
                ),
            )
        # initialize filters with gabors
        f = np.geomspace(1, 10, self.n_filt // 2).astype("float32")
        gw0 = keypoints.gabor_wavelet(1, f[:, np.newaxis], 0, n_pts=kernel_size)
        gw1 = keypoints.gabor_wavelet(1, f[:, np.newaxis], np.pi / 2, n_pts=kernel_size)
        wav_init = np.vstack((gw0, gw1))
        # compute n_filt wavelet features of each one => n_filt * n_kp features
        self.features.add_module(
            "wavelet0",
            nn.Conv1d(1, self.n_filt, kernel_size=kernel_size,
                      padding=kernel_size // 2, bias=False,
            ),
        )
        self.features[-1].weight.data = torch.from_numpy(wav_init).unsqueeze(1)
    
        for n in range(1, n_layers):
            n_in = self.n_kp * self.n_filt if n == 1 else n_med
            self.features.add_module(
                f"linear{n}",
                nn.Sequential(
                    nn.Linear(n_in, n_med),
                ),
            )

        # latent linear layer
        n_med = n_med if n_layers > 1 else self.n_filt * self.n_kp
        self.features.add_module(
            "latent",
            nn.Sequential(
                nn.Linear(n_med, n_latents),
            ),
        )

    def wavelets(self, x):
        """compute wavelets of keypoints through linear + conv1d + relu layer"""
        # x is (n_batches, time, features)
        out = self.features[0](x.reshape(-1, x.shape[-1]))
        out = out.reshape(x.shape[0], x.shape[1], -1).transpose(2, 1)
        # out is now (n_batches, n_kp, time)
        out = out.reshape(-1, out.shape[-1]).unsqueeze(1)
        # out is now (n_batches * n_kp, 1, time)
        out = self.features[1](out)
        # out is now (n_batches * n_kp, n_filt, time)
        out = out.reshape(-1, self.n_kp * self.n_filt, out.shape[-1]).transpose(
            2, 1
        )
        out = out.reshape(-1, self.n_kp * self.n_filt)
        if self.relu_wavelets:
            out = F.relu(out)

        # if n_layers > 1, go through more linear layers
        for n in range(1, self.n_layers):
            out = self.features[n + 1](out)
            out = F.relu(out)
        return out

    def forward(self, x=None, wavelets=None):
        """x is (n_batches, time, features)
        sample_inds is (sub_time) over batches
        """
        if wavelets is None:
            wavelets = self.wavelets(x)
        wavelets = wavelets.reshape(-1, wavelets.shape[-1])

        # latent layer
        latents = self.features[-1](wavelets)
        latents = latents.reshape(x.shape[0], -1, latents.shape[-1])
        if self.relu_latents:
            latents = F.relu(latents)
        latents = latents.reshape(-1, latents.shape[-1])
        return latents


class Readout(nn.Module):
    """
    Linear layer from latents to neural PCs or neurons
    """

    def __init__(self, n_animals=1, n_latents=256, n_layers=1, n_med=128, n_out=128):
        super().__init__()
        self.n_animals = n_animals
        self.features = nn.Sequential()
        self.bias = nn.Parameter(torch.zeros(n_out))
        if n_animals == 1:
            for j in range(n_layers):
                n_in = n_latents if j == 0 else n_med
                n_outc = n_out if j == n_layers - 1 else n_med
                self.features.add_module(f"linear{j}", nn.Linear(n_in, n_outc))
                if n_layers > 1 and j < n_layers - 1:
                    self.features.add_module(f"relu{j}", nn.ReLU())
        else:
            # no option for n_layers > 1
            for n in range(n_animals):
                self.features.add_module(f"linear0_{n}", nn.Linear(n_latents, n_out))
        self.bias.requires_grad = False

    def forward(self, latents, animal_id=0):
        if self.n_animals == 1:
            return self.features(latents) + self.bias
        else:
            return self.features[animal_id](latents) + self.bias
