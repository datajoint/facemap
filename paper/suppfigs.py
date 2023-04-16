import fig4
import matplotlib.pyplot as plt
import torch
from fig_utils import *
from rastermap import sorting
from scipy.stats import wilcoxon, zscore

from facemap.utils import bin1d

def varexp_ranks(data_path, dbs, evals=None, save_fig=False):
    colors = [[0.5, 0.5, 0.5], [0.75, 0.75, 0.25]]
    lbls = ["keypoints", "movie PCs"]

    fig = plt.figure(figsize=(9,3))
    trans = mtransforms.ScaledTranslation(-50 / 72, 7 / 72, fig.dpi_scale_trans)
    grid = plt.GridSpec(
            1,
            3,
            figure=fig,
            left=0.15,
            right=0.95,
            top=0.9,
            bottom=0.2,
            wspace=0.5,
            hspace=0.25,
    )
        
    mstrs = [f"{db['mname']}_{db['datexp']}_{db['blk']}" for db in dbs]
    ve = np.zeros((len(dbs), 128, 2))
    evals = np.zeros((len(dbs), 500)) if evals is None else evals
    for iexp, mstr in enumerate(mstrs):
        if evals[iexp].sum()==0:
            svd_path = f"{data_path}cam/cam0_{mstr}_proc.npy"
            svds = np.load(svd_path, allow_pickle=True).item()
            ev = (svds["movSVD"][0]**2).sum(axis=0)
            evals[iexp] = ev / ev.sum()
        d = np.load(f"{data_path}/proc/neuralpred/{mstr}_rrr_pred_test.npz")
        ve[iexp,:] = d['varexp'][:128, ::-1] * 100
        #plt.semilogx(np.arange(1, len(d['varexp'])+1), )
        
    il = 0
    ax = plt.subplot(grid[0,0])
    il = plot_label(ltr, il, ax, trans, fs_title)
    vem = evals.mean(axis=0)
    ves = evals.std(axis=0) / (evals.shape[0]-1)**0.5
    ax.loglog(np.arange(1,501), vem, color='k')
    ax.fill_between(
        np.arange(1, 501), vem + ves, vem - ves, color='k', alpha=0.25
    )
    ax.set_ylabel('fraction of variance')
    ax.set_xlabel('PC dimension')
    ax.set_title(
        "face movie PCs", fontweight="bold", fontsize="medium"
    )
            
    colors = [[0.5, 0.5, 0.5], [0.75, 0.75, 0.25]]
    lbls = ["keypoints", "movie PCs"]

    vis = np.array([db["visual"] for db in dbs])
    ranks = np.arange(1,129)
    for j, inds in enumerate([vis, ~vis]):
        ax = plt.subplot(grid[0,j+1])
        if j==0:
            il = plot_label(ltr, il, ax, trans, fs_title)
        for i in range(2):
            vem = ve[inds,:,i].mean(axis=0)
            ves = ve[inds,:,i].std(axis=0) / ((inds.sum()-1)**0.5)
            #print(vem+ves - (vem-ves))
            ax.plot(ranks, vem, color=colors[i])
            ax.fill_between(
                    ranks, vem + ves, vem - ves, color=colors[i], alpha=0.25
                )
            if j == 0:
                x = 0.6
                y = 0.1 + i * 0.12
                ax.text(
                    x, y, lbls[i], color=colors[i], transform=ax.transAxes
                )
                
        if j == 0:
            #il = plot_label(ltr, il, ax, trans, fs_title)
            ax.set_ylabel("% variance explained, \ntop 128 PCs (test data)")
            ax.set_title(
                "visual", fontweight="bold", color=viscol, fontsize="medium"
            )
        else:
            ax.set_title(
                "sensorimotor", fontweight="bold", color=smcol, fontsize="medium"
            )
        ax.set_xlabel("ranks")
        ax.set_xscale("log")
        ax.set_xticks([1,4,16,64,128])
        ax.set_xticklabels(["1", "4", "16", "32", "128"])
        ax.set_xlim([1,128])
        ax.set_ylim([0, 38])

    if save_fig:
        fig.savefig(f"{data_path}figs/suppfig_veranks.pdf")

    return evals


def varexp_AP(data_path, dbs, save_fig=False):
    mstrs = [f"{db['mname']}_{db['datexp']}_{db['blk']}" for db in dbs]
    ve_overall = np.zeros((len(dbs), 3, 128))
    nbins = 5
    improvement = np.zeros((len(dbs), nbins))
    ve_all = np.zeros((len(dbs), nbins))
    xposs = []
    yposs = []
    ccol = []
    for iexp, mstr in enumerate(mstrs):
        dat = np.load(f"{data_path}/neural_data/spont_{mstr}.npz")
        inds = dat["xpos"].argsort()
        nneus = np.linspace(0, len(inds), nbins + 1).astype(int)
        ve_net = np.load(f"{data_path}/proc/neuralpred/{mstr}_net_pred_test.npz")[
            "varexp_neurons"
        ][:, 1]
        ve_lin = np.load(f"{data_path}/proc/neuralpred/{mstr}_rrr_pred_test.npz")[
            "varexp_neurons"
        ][1]

        # ve_svd = np.load(f"{data_path}/proc/neuralpred/{mstr}_svd_pred_test.npz")[
        #    "varexp_neurons"
        # ]
        for i in range(nbins):
            ineu = inds[nneus[i] : nneus[i + 1]]
            ve0 = ve_net[ineu].mean()
            ve1 = ve_lin[ineu].mean()
            improvement[iexp, i] = ((ve0 - ve1) / ve1) * 100

        if iexp == 2 or iexp == 10:
            cc = ((ve_net - ve_lin) / (ve_lin)) * 100
            igood = ve_lin > 1e-2
            xposs.append(dat["xpos"][igood])
            yposs.append(dat["ypos"][igood])
            ccol.append(cc[igood])

    fig = plt.figure(figsize=(12, 3))
    yratio = 12 / 3
    trans = mtransforms.ScaledTranslation(-25 / 72, 20 / 72, fig.dpi_scale_trans)
    grid = plt.GridSpec(
        1,
        7,
        figure=fig,
        left=0.05,
        right=0.95,
        top=0.8,
        bottom=0.1,
        wspace=0.75,
        hspace=0.75,
    )
    il = 0
    for i in range(2):
        xpos, ypos, c = xposs[i], -1 * yposs[i], ccol[i]
        ax = plt.subplot(grid[0, i * 2 : (i + 1) * 2])
        il = plot_label(ltr, il, ax, trans, fs_title)
        if i == 1:
            pos = ax.get_position()
            ax.axis("off")
            pos = [pos.x0, pos.y0, pos.width, pos.height]
            ax = fig.add_axes(
                [pos[0] - 0.025, pos[1] - 0.02, pos[2] + 0.06, pos[3] + 0.06]
            )
        else:
            ax.set_title("net prediction improvement\nover linear", fontsize="medium")

            pos = ax.get_position()
            ax.axis("off")
            pos = [pos.x0, pos.y0, pos.width, pos.height]
            ax = fig.add_axes(pos)

            add_apml(ax, xpos, ypos)

        im = ax.scatter(
            ypos,
            xpos,
            c=c,
            vmin=-300,
            vmax=300,
            cmap="bwr",
            s=1,
            alpha=1,
            rasterized=True,
        )
        ax.axis("square")
        ax.axis("off")
        if i == 0:
            plt.colorbar(im, label="% improvement", shrink=0.5)

    colors = [viscol, smcol]
    vis = np.array([db["visual"] for db in dbs])
    trans = mtransforms.ScaledTranslation(-50 / 72, 20 / 72, fig.dpi_scale_trans)
    for i, inds in enumerate([vis, ~vis]):
        ax = plt.subplot(grid[0, 4 + i])
        pos = ax.get_position()
        ax.axis("off")
        pos = [pos.x0, pos.y0, pos.width, pos.height]
        ax = fig.add_axes([pos[0] - 0.07, pos[1], pos[2], pos[3]])
        impr = improvement[inds]
        plt.plot(impr.T, color=colors[i], alpha=0.5)
        plt.errorbar(
            np.arange(0, impr.shape[1]),
            impr.mean(axis=0),
            impr.std(axis=0) / impr.shape[0] ** 0.5,
            color=colors[i],
            lw=3,
        )
        plt.ylim([0, 300])
        ax.set_xticks([0, 4])
        ax.set_xticklabels(["posterior", "anterior"])
        if i == 0:
            il = plot_label(ltr, il, ax, trans, fs_title)
            ax.set_ylabel("% improvement")
            ax.set_title("visual", fontsize="medium")
        else:
            ax.set_title("sensorimotor", fontsize="medium")

    ax = plt.subplot(grid[6])
    pos = ax.get_position()
    ax.axis("off")
    pos = [pos.x0, pos.y0, pos.width, pos.height]
    ax = fig.add_axes([pos[0] - 0.03, pos[1], pos[2] + 0.06, pos[3]])
    mstrs = [f"{db['mname']}_{db['datexp']}_{db['blk']}" for db in dbs]
    ve_all = []
    for j, mstr in enumerate(mstrs):
        d = np.load(f"{data_path}/proc/neuralpred/{mstr}_kpareas_pred_test.npz")
        ve_expl = np.load(f"{data_path}/proc/neuralpred/{mstr}_spks_test.npz")[
            "varexp_expl_neurons"
        ].mean()
        kpa = d["varexp_neurons"].mean(axis=0)
        kpareas = d["kpareas"]
        vef = np.load(f"{data_path}/proc/neuralpred/{mstr}_net_pred_test.npz")[
            "varexp_neurons"
        ][:, 1]
        kpf = np.array([vef.mean(), *kpa]) / ve_expl * 100
        ve_all.append(kpf)
    ve_all = np.array(ve_all)
    for i, inds in enumerate([vis, ~vis]):
        print(ve_all[inds].mean(axis=0))
        ax.plot(ve_all[inds].T, color=viscol if i == 0 else smcol, lw=1, alpha=0.5)
        plt.errorbar(
            np.arange(0, 4),
            ve_all[inds].mean(axis=0),
            ve_all[inds].std(axis=0) / inds.sum() ** 0.5,
            color=viscol if i == 0 else smcol,
            lw=3,
            zorder=5,
        )

    ax.set_title("Prediction from \nkeypoint groups", fontsize="medium")
    ax.set_ylim([0, 72])
    ax.set_xticks(np.arange(0, 4))
    ax.set_xticklabels(["all", "eye  ", "whisker", "  nose"])
    ax.set_ylabel("% normalized variance\nexplained (test data)")
    il = plot_label(ltr, il, ax, trans, fs_title)

    if save_fig:
        fig.savefig(f"{data_path}figs/suppfig_varexpAP.pdf")


def example_sm(data_path, db, save_fig=False):
    fig = plt.figure(figsize=(9.5 * 0.75, 7.8))
    trans = mtransforms.ScaledTranslation(-30 / 72, 7 / 72, fig.dpi_scale_trans)
    grid = plt.GridSpec(
        4,
        1,
        figure=fig,
        left=0.1,
        right=0.97,
        top=0.95,
        bottom=0.03,
        wspace=0.75,
        hspace=0.25,
    )
    il = 0

    il = fig4.panels_activity(data_path, db, grid, trans, il, tmin=0)
    if save_fig:
        fig.savefig(f"{data_path}figs/suppfig_examplesm.pdf")


def example_clusters(data_path, dbs, save_fig=False):
    fig = plt.figure(figsize=(14, 14))
    yratio = 1
    trans = mtransforms.ScaledTranslation(-30 / 72, 7 / 72, fig.dpi_scale_trans)
    grid = plt.GridSpec(
        2,
        1,
        figure=fig,
        left=0.05,
        right=0.97,
        top=0.97,
        bottom=0.03,
        wspace=0.75,
        hspace=0.25,
    )
    subsample = 10
    il = 0
    sc = [0.9, 0.75]
    for k, db in enumerate(dbs):
        ax = plt.subplot(grid[k, 0])
        clust_kl_ve = np.load(
            f"{data_path}/proc/neuralpred/{db['mname']}_{db['datexp']}_{db['blk']}_clust_kl_ve.npz"
        )
        labels = clust_kl_ve["labels"]
        ve_clust = clust_kl_ve["varexp_clust"]
        kl_clust = clust_kl_ve["kl_clust"]
        ct = clust_kl_ve["clust_test"]
        cp = clust_kl_ve["clust_pred_test"]
        cc = (zscore(ct, axis=0) * zscore(cp, axis=0)).mean(axis=0)

        xypos = [clust_kl_ve["xpos"], clust_kl_ve["ypos"]]

        grid1 = matplotlib.gridspec.GridSpecFromSubplotSpec(
            5,
            20,
            subplot_spec=grid[k, 0],
            hspace=[0.2, 1.0][k],
        )
        for i, ind in enumerate(kl_clust.argsort()):
            ax = plt.subplot(grid1[i // 20, i % 20])
            ax.axis("off")
            pos = ax.get_position()
            pos = [pos.x0, pos.y0, pos.width, pos.height]
            ypos, xpos = -xypos[1], xypos[0]
            ylim = np.array([ypos.min(), ypos.max()])
            xlim = np.array([xpos.min(), xpos.max()])
            ylr = np.diff(ylim)[0] / np.diff(xlim)[0]
            ax = grid1.figure.add_axes(
                [pos[0], pos[1], pos[2] * sc[k], pos[2] * sc[k] / ylr * yratio]
            )
            if i == 0:
                il = plot_label(ltr, il, ax, trans, fs_title)
            ax.scatter(
                ypos[::subsample],
                xpos[::subsample],
                s=1,
                color=[0.9, 0.9, 0.9],
                rasterized=True,
            )
            ax.scatter(ypos[labels == ind], xpos[labels == ind], s=3, rasterized=True)
            ax.set_title(f"LI={kl_clust[ind]:.2f}\nr={cc[ind]:.2f}", fontsize="medium")
            ax.set_xlim(ylim)
            ax.set_ylim(xlim)
            ax.axis("off")

    if save_fig:
        fig.savefig(f"{data_path}figs/suppfig_exampleclusters.pdf")


def model_complexity(data_path, dbs, save_fig=False):
    mstrs = [f"{db['mname']}_{db['datexp']}_{db['blk']}" for db in dbs]
    d = np.load(f"{data_path}/proc/neuralpred/{mstrs[0]}_complexity.npz")
    n_latents = d["n_latents"]
    n_filts = d["n_filts"]
    ve_no_param = np.zeros((len(dbs), 4))
    ve_nl_all = np.zeros((len(dbs), 5, 2))
    ve_latents = np.zeros((len(dbs), len(n_latents)))
    ve_filts = np.zeros((len(dbs), len(n_filts)))

    for iexp, mstr in enumerate(mstrs):
        d = np.load(f"{data_path}/proc/neuralpred/{mstr}_complexity.npz")
        ve_expl = np.load(f"{data_path}/proc/neuralpred/{mstr}_spks_test.npz")[
            "varexp_expl_neurons"
        ].mean()
        ve_no_param[iexp] = (
            d["varexps_no_param_neurons"].mean(axis=-1) / ve_expl
        ) * 100
        ve_nl_all[iexp] = (d["varexps_nl_all_neurons"].mean(axis=1).T / ve_expl) * 100
        ve_latents[iexp] = (d["varexps_latents_neurons"].mean(axis=0) / ve_expl) * 100
        ve_filts[iexp] = (d["varexps_filts_neurons"].mean(axis=0) / ve_expl) * 100

    fig = plt.figure(figsize=(12, 4))
    yratio = 11 / 4
    trans = mtransforms.ScaledTranslation(-40 / 72, 20 / 72, fig.dpi_scale_trans)
    grid = plt.GridSpec(
        1,
        5,
        figure=fig,
        left=0.1,
        right=0.95,
        top=0.8,
        bottom=0.4,
        wspace=0.5,
        hspace=1,
    )
    il = 0

    vis = np.array([db["visual"] for db in dbs])
    ylim = [38, 50]
    colors = [viscol, smcol]

    ax = plt.subplot(grid[0, 0])
    il = plot_label(ltr, il, ax, trans, fs_title)
    i0 = 4
    for j, inds in enumerate([vis, ~vis]):
        ax.plot(n_latents, ve_latents[inds].mean(axis=0), color=colors[j])
        ax.scatter(
            n_latents[i0],
            ve_latents[inds, i0].mean(axis=0),
            marker="*",
            color=colors[j],
            s=150,
        )
    ax.set_xlabel("# of deep\nbehavioral features")
    ax.set_ylim([0, 52])
    ax.set_xscale("log")
    xts = 2.0 ** np.arange(0, 11, 2)
    ax.set_xticks(xts)
    ax.set_xticklabels(
        ["1", "4", "16 ", "64 ", "256 ", "   1024"], fontsize="small"
    )  # , rotation=45, ha='right')

    ax.set_ylabel("% normalized variance\n explained (test data)")

    i0 = [1, 0]
    lstr = ["core", "readout"]
    for k in range(2):
        ax = plt.subplot(grid[0, 1 + k])
        il = plot_label(ltr, il, ax, trans, fs_title)
        for j, inds in enumerate([vis, ~vis]):
            ax.plot(
                np.arange(1, 6), ve_nl_all[inds, :, k].mean(axis=0), color=colors[j]
            )
            ax.scatter(
                i0[k] + 1,
                ve_nl_all[inds, i0[k], k].mean(axis=0),
                marker="*",
                color=colors[j],
                s=150,
            )
        ax.set_ylim(ylim)
        ax.set_xlim([0.5, 5.5])
        ax.set_xticks(np.arange(1, 6))
        ax.set_xlabel(f"# of {lstr[k]} layers")

    ax = plt.subplot(grid[0, 3])
    il = plot_label(ltr, il, ax, trans, fs_title)
    i0 = 0
    for j, inds in enumerate([vis, ~vis]):
        ax.plot(ve_no_param[inds].mean(axis=0), color=colors[j])
        ax.scatter(
            i0, ve_no_param[inds, i0].mean(axis=0), marker="*", color=colors[j], s=150
        )
    ax.set_ylim(ylim)
    ax.set_xticks(np.arange(0, 4))
    ax.set_xticklabels(
        ["normal", "w/o 1st linear layer", "w/o ReLU conv layer", "w/o ReLU deep beh."],
        rotation=45,
        ha="right",
    )

    ax = plt.subplot(grid[0, 4])
    il = plot_label(ltr, il, ax, trans, fs_title)
    i0 = 2
    for j, inds in enumerate([vis, ~vis]):
        ax.plot(n_filts, ve_filts[inds].mean(axis=0), color=colors[j])
        ax.scatter(
            n_filts[i0],
            ve_filts[inds, i0].mean(axis=0),
            marker="*",
            color=colors[j],
            s=150,
        )
    ax.set_xscale("log")
    ax.set_ylim(ylim)
    ax.set_xlabel("# of convolution \nfilters")
    ax.set_xticks([2, 10, 50])
    ax.set_xticklabels(["2", "10", "50"])

    for iexp, mstr in enumerate(mstrs):
        d = np.load(f"{data_path}/proc/neuralpred/{mstr}_complexity.npz")
        ve_expl = np.load(f"{data_path}/proc/neuralpred/{mstr}_spks_test.npz")[
            "varexp_expl_neurons"
        ].mean()
        ve_no_param[iexp] = (
            d["varexps_no_param_neurons"].mean(axis=-1) / ve_expl
        ) * 100
        ve_nl_all[iexp] = (d["varexps_nl_all_neurons"].mean(axis=1).T / ve_expl) * 100
        ve_latents[iexp] = (d["varexps_latents_neurons"].mean(axis=0) / ve_expl) * 100
        ve_filts[iexp] = (d["varexps_filts_neurons"].mean(axis=0) / ve_expl) * 100

    if save_fig:
        fig.savefig(f"{data_path}figs/suppfig_complexity.pdf")
