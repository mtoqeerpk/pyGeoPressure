# -*- coding: utf-8 -*-
"""
class for interfacing with segy file.

Created on Feb. 7th 2018
"""
from __future__ import division, print_function

__author__ = "yuhao"

import sqlite3
import os
import json
from shutil import copyfile
from builtins import range
from itertools import product

import numpy as np

from . import Path

import segyio

from .utils import split_sequence, methdispatch
from .vawt import wiggles, img
from .indexes import InlineIndex, CrlineIndex, DepthIndex, CdpIndex
from .well_log import Log


class SeiSEGY(object):
    def __init__(self, segy_file, like=None):
        self.segy_file = segy_file

        if like is not None:
            if Path(like).exists() and not Path(self.segy_file).exists():
                copyfile(src=like, dst=self.segy_file)

        if self.segy_file is not None:
            self._parse_segy()

    def _info(self):
        return "A seismic Data Cube\n" +\
               'In-line range: {} - {} - {}\n'.format(
                   self.startInline, self.endInline, self.stepInline) +\
               'Cross-line range: {} - {} - {}\n'.format(
                   self.startCrline, self.endCrline, self.stepCrline) +\
               'Z range: {} - {} - {}\n'.format(
                   self.startDepth, self.endDepth, self.stepDepth)

    def __str__(self):
        return self._info()

    def __repr__(self):
        return self._info()

    def _parse_segy(self):
        with segyio.open(self.segy_file, 'r') as segyfile:
            segyfile.mmap()
            self.startInline = segyfile.ilines[0]
            self.endInline = segyfile.ilines[-1]
            self.nEast = len(segyfile.ilines)
            self.stepInline = (self.endInline - self.startInline) // \
                (self.nEast - 1)
            self.startCrline = segyfile.xlines[0]
            self.endCrline = segyfile.xlines[-1]
            self.nNorth = len(segyfile.xlines)
            self.stepCrline = (self.endCrline - self.startCrline) // \
                (self.nNorth - 1)
            # self.startDepth = segyfile.bin[segyio.BinField.SamplesOriginal]
            # # in miliseconds
            # self.stepDepth = segyfile.bin[segyio.BinField.Interval] // 1000
            # self.nDepth = segyfile.bin[segyio.BinField.Samples]
            # self.endDepth = self.startDepth + self.stepDepth * (self.nDepth - 1)
            self.startDepth = segyfile.samples[0]
            self.endDepth = segyfile.samples[-1]
            self.nDepth = len(segyfile.samples)
            self.stepDepth = (self.endDepth - self.startDepth) // \
                (self.nDepth - 1)

    def inlines(self):
        """
        Iterator for inline numbers
        """
        for inline in range(self.startInline, self.endInline+1, self.stepInline):
            yield inline

    def crlines(self):
        """
        Iterator for crline numbers
        """
        for crline in range(self.startCrline, self.endCrline+1, self.stepCrline):
            yield crline

    def inline_crlines(self):
        """
        Iterator for both inline and crline numbers
        """
        for inline, crline in product(
                range(self.startInline, self.endInline+1, self.stepInline),
                range(self.startCrline, self.endCrline+1, self.stepCrline)):
            yield (inline, crline)

    def depths(self):
        """
        Iterator for z coordinate
        """
        for i in range(self.nDepth):
            yield self.startDepth + i * self.stepDepth

    def inline(self, inline):
        with segyio.open(self.segy_file, 'r') as segyfile:
            segyfile.mmap()
            data = segyfile.iline[inline]
        return data

    def crline(self, crline):
        with segyio.open(self.segy_file, 'r') as segyfile:
            segyfile.mmap()
            data = segyfile.xline[crline]
        return data

    def depth(self, depth):
        with segyio.open(self.segy_file, 'r') as segyfile:
            segyfile.mmap()
            data = segyfile.depth_slice[depth]
        return data

    def cdp(self, cdp):
        with segyio.open(self.segy_file, 'r') as segyfile:
            segyfile.mmap()
            data = segyfile.gather[cdp]
        return data

    @methdispatch
    def data(self, indexes):
        raise TypeError("Unsupported Type")

    @data.register(InlineIndex)
    def _(self, indexes):
        return self.inline(indexes.value)

    @data.register(CrlineIndex)
    def _(self, indexes):
        return self.crline(indexes.value)

    @data.register(DepthIndex)
    def _(self, indexes):
        return self.depth(indexes.value)

    @data.register(CdpIndex)
    def _(self, indexes):
        return self.cdp(indexes.value)

    def update(self, index, data):
        try:
            if not isinstance(index, InlineIndex):
                raise TypeError("has to be InlineIndex")
            if data.shape != (self.nNorth, self.nDepth):
                raise ValueError
            with segyio.open(self.segy_file, 'r+') as segyfile:
                segyfile.mmap()
                segyfile.iline[index.value] = data
        except Exception as er:
            print(er.message)

    @methdispatch
    def plot(self, index, ax, kind='vawt', cm='seismic', ptype='seis'):
        raise TypeError('Unsupported index type')

    @plot.register(InlineIndex)
    def _(self, index, ax, kind='vawt', cm='seismic', ptype='seis'):
        data = self.data(index)
        if kind == 'vawt':
            wiggles(data.T, wiggleInterval=1, ax=ax)
        elif kind == 'img':
            img(data.T,
                extent=[
                    self.startCrline, self.endCrline,
                    self.startDepth, self.endDepth],
                ax=ax, cm=cm, ptype=ptype)
            ax.invert_yaxis()
        else:
            pass
        ax.get_figure().suptitle('In-line Section: {}'.format(index.value))
        from matplotlib.offsetbox import AnchoredText
        z_text = AnchoredText(
            r"$\downarrow$Z",
            loc=2, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(0., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(z_text)
        inline_text = AnchoredText(
            r"Cross-line $\rightarrow$ ",
            loc=1, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(1., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(inline_text)

    @plot.register(CrlineIndex)
    def _(self, index, ax, kind='vawt', cm='seismic', ptype='seis'):
        data = self.data(index)
        if kind == 'vawt':
            wiggles(data.T, wiggleInterval=1, ax=ax)
        elif kind == 'img':
            img(data.T,
                extent=[
                    self.startInline, self.endInline,
                    self.startDepth, self.endDepth],
                ax=ax, cm=cm, ptype=ptype)
            ax.invert_yaxis()
        else:
            pass
        ax.get_figure().suptitle('Cross-line Section: {}'.format(index.value))
        from matplotlib.offsetbox import AnchoredText
        z_text = AnchoredText(
            r"$\downarrow$Z",
            loc=2, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(0., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(z_text)
        inline_text = AnchoredText(
            r"In-line $\rightarrow$ ",
            loc=1, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(1., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(inline_text)

    @plot.register(DepthIndex)
    def _(self, index, ax, kind='vawt', cm='seismic', ptype='seis'):
        data = self.data(index)
        if kind == 'vawt':
            wiggles(data.T, wiggleInterval=1, ax=ax)
        elif kind == 'img':
            img(data.T,
                extent=[
                    self.startInline, self.endInline,
                    self.startCrline, self.endCrline,],
                ax=ax, cm=cm, ptype=ptype)
            ax.invert_yaxis()
        else:
            pass
        ax.get_figure().suptitle("Z slice: {}".format(index.value))
        from matplotlib.offsetbox import AnchoredText
        z_text = AnchoredText(
            r"$\downarrow$Cross-line",
            loc=2, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(0., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(z_text)
        inline_text = AnchoredText(
            r"In-line $\rightarrow$ ",
            loc=1, prop=dict(size=10), frameon=False,
            bbox_to_anchor=(1., 0.),
            bbox_transform=ax.transAxes)
        ax.add_artist(inline_text)

    # def get_pseudo_log(self, cdp):
    #     pseudo_log = Log()
    #     pseudo_log.depth = list(self.depth())
    #     pseudo_log.data = self.get_data(CdpIndex(cdp))
    #     pseudo_log.name = "{}_inline_{}_crline_{}".format(attr, cdp[0], cdp[1])
    #     return pseudo_log

    def valid_cdp(self, cdp_num):
        inl_num, crl_num = cdp_num
        n_inline = (inl_num - self.startInline) // self.stepInline
        in_plus_one = round(((inl_num - self.startInline) % self.stepInline) / \
                            self.stepInline)
        inline = self.startInline + (n_inline + in_plus_one) * self.stepInline

        n_crline = (crl_num - self.startCrline) // self.stepCrline
        cr_plus_one = round(((crl_num - self.startCrline) % self.stepCrline) / \
                            self.stepCrline)
        crline = self.startCrline + (n_crline + cr_plus_one) * self.stepCrline
        return (inline, crline)

