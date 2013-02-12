#!/usr/bin/env python

'''
Star detection module

Fit fluxes and star data to an extinction law to obtain 
extinction and instrument zeropoint.
____________________________

This module is part of the PyASB project, 
created and maintained by Miguel Nievas [UCM].
____________________________
'''

DEBUG=False

__author__ = "Miguel Nievas"
__copyright__ = "Copyright 2012, PyASB project"
__credits__ = ["Miguel Nievas"]
__license__ = "GNU GPL v3"
__shortname__ = "PyASB"
__longname__ = "Python All-Sky Brightness pipeline"
__version__ = "1.99.0"
__maintainer__ = "Miguel Nievas"
__email__ = "miguelnr89[at]gmail[dot]com"
__status__ = "Prototype" # "Prototype", "Development", or "Production"


try:
	import matplotlib.pyplot as mpl
	import matplotlib.colors as mpc
	import matplotlib.patches as mpp
	import scipy.stats as stats
	import math
	import numpy as np
	import astrometry
except:
	print 'One or more modules missing: numpy,scipy,math,matplotlib,astrometry'
	raise SystemExit

class BouguerFit():
	def __init__(self,ImageInfo,PhotometricCatalog):
		print('Fitting Bouguer Law to derive extinction and zeropoint ...')
		self.bouguer_fit(ImageInfo,PhotometricCatalog)
		if DEBUG==True:
			print(len(StarCatalog.StarList))
	
	def bouguer_fit(self,ImageInfo,StarCatalog):
		''' 
		Fit measured fluxes to an extinction model
		Return regression parameters (ZeroPoint, Extinction)
		'''
		
		self.xdata    = [Star.airmass for Star in StarCatalog.StarList]
		self.ydata    = [Star.m25logF for Star in StarCatalog.StarList]
		self.yerr = [Star.m25logF_unc for Star in StarCatalog.StarList]
			
		try:
			fixed_y     = ImageInfo.zeropoint
			fixed_y_unc = ImageInfo.zeropoint_unc
			self.Regression = TheilSenRegression(self.xdata,self.ydata,self.fixed_y,self.fixed_y_unc)
		except:
			try:
				self.Regression = TheilSenRegression(self.xdata,self.ydata)
			except:
				raise
	
	def bouguer_plot(self,ImageInfo,ObsPyephem):
		''' Plot photometric data from the bouguer fit '''
	
		xfit = np.linspace(1,astrometry.calculate_airmass(ImageInfo.min_altitude),10)
		yfit = np.polyval([self.Regression.mean_slope,self.Regression.mean_zeropoint],xfit)
	
		bouguerfigure = mpl.figure(figsize=(8,6),dpi=100)
		bouguerplot = bouguerfigure.add_subplot(111)
		bouguerplot.set_title('Bouguer extinction law fit',size="xx-large")
		bouguerplot.errorbar(self.xdata, self.ydata, yerr=self.yerr, fmt='*', ecolor='g')
		bouguerplot.plot(xfit,yfit,'r-')
		
		try:
			plot_infotext = \
				ImageInfo.date_string+str(ObsPyephem.lat)+5*" "+str(ObsPyephem.lon)+"\n"+\
				ImageInfo.used_filter+4*" "+"Rcorr="+str("%.3f"%float(self.Regression.kendall_tau))+"\n"+\
				"C="+str("%.3f"%float(self.Regression.mean_zeropoint))+"+/-"+str("%.3f"%float(self.Regression.error_zeropoint))+"\n"+\
				"K="+str("%.3f"%float(self.Regression.mean_slope))+"+/-"+str("%.3f"%float(self.Regression.error_slope))+"\n"+\
				str("%.0f"%(100.*self.Regression.Nstars_rel))+"% of "+str(self.Regression.Nstars_initial)+" photometric measures shown"
			bouguerplot.text(0.1,0.1,plot_infotext,fontsize='x-small',transform = bouguerplot.transAxes)
		except:
			raise
		
		if ImageInfo.bouguerplot_file!=False:
			# Show or save the bouguer plot
			bouguerfigure.savefig("/home/minaya/prueba.png")
			show_or_save_bouguerplot(bouguerfigure,ImageInfo,ObsPyephem)

class TheilSenRegression():
	# Robust Theil Sen estimator, instead of the classic least-squares.
	def __init__(self,Xpoints,Ypoints,y0=None,y0err=None,x0=None,x0err=None):
		assert(len(Xpoints)==len(Ypoints) and len(Ypoints)>2)
		self.Xpoints = np.array(Xpoints)
		self.Ypoints = np.array(Ypoints)
		if y0!=None:
			self.fixed_zp = True
			if y0err!=None:
				self.y0err=y0err
			else: 
				self.y0err=0.0
			
			if x0!=None:
				self.x0 = x0
				if x0err!=None:
					self.x0err = 0.0
			else:
				self.x0 = 0.0
				self.x0err = 0.0
		else: self.fixed_zp = False
		self.Nstars_initial = len(self.Ypoints)
		self.Nstars_final = self.Nstars_initial
		self.pair_blacklist = []
		# Perform the regression
		self.perform_regression()
		self.Nstars_rel = 100.*self.Nstars_final/self.Nstars_initial
		
	def perform_regression(self):
		# Prepare data for regression
		self.build_matrix_values()
		self.build_complementary_matrix()
		self.build_slopes_matrix()
		self.upper_diagonal_slope_matrix_values()
		# Slope
		self.calculate_mean_slope()
		# Zero point
		self.build_zeropoint_array()
		self.calculate_mean_zeropoint()
		# Errors and fit quality
		self.calculate_residuals()
		self.calculate_kendall_tau()
		self.calculate_errors()
		if self.fixed_zp == True:
			self.mean_zeropoint = self.y0
			self.error_zeropoint = self.y0err
		self.Nstars_final = len(self.Ypoints)
	
	def build_matrix_values(self):
		self.X_matrix_values = \
			np.array([[column for column in self.Xpoints] for line in self.Xpoints])
		self.Y_matrix_values = \
			np.array([[line for line in self.Ypoints] for line in self.Ypoints])
	
	def build_complementary_matrix(self):	
		if self.fixed_zp == False:
			self.X_complementary_values = self.X_matrix_values.transpose()
			self.Y_complementary_values = self.Y_matrix_values.transpose()
		if self.fixed_zp == True:
			self.X_complementary_values = np.array([[self.x0\
				for column in self.Xpoints] for line in self.Xpoints])
			self.Y_complementary_values = np.array([[self.y0\
				for column in self.Ypoints] for line in self.Ypoints])
	
	def build_slopes_matrix(self):
		self.slopes_matrix = \
			((self.Y_matrix_values-self.Y_complementary_values +1e-20)/ \
			(self.X_matrix_values-self.X_complementary_values +1e-20))
		# +1e-20 lets us hide Numpy warning with 0/0
	
	def upper_diagonal_slope_matrix_values(self):
		self.upper_diag_slopes = \
			np.array([self.slopes_matrix[l][c] \
			for l in xrange(len(self.slopes_matrix)) \
			for c in xrange(len(self.slopes_matrix[0])) if c>l])
	
	def calculate_mean_slope(self):
		self.mean_slope  = np.median(self.upper_diag_slopes)
		
	def build_zeropoint_array(self):
		self.zeropoint_array = self.Ypoints - self.Xpoints*self.mean_slope
	
	def calculate_mean_zeropoint(self):
		self.mean_zeropoint  = np.median(self.zeropoint_array)
		
	def calculate_residuals(self):
		self.residuals = self.zeropoint_array-self.mean_zeropoint
		
	def calculate_errors(self):
		xmedcuad = np.median(self.Xpoints)**2
		xcuaddif = self.Xpoints**2 - xmedcuad
		xdensity = np.sum(xcuaddif)
		sigma2_res = (1./(self.Nstars_final-2))*abs(sum(self.residuals))
		sigma2_slope = sigma2_res/abs(xdensity)
		sigma2_int = sigma2_res*(1./self.Nstars_final + 1.*xmedcuad/abs(xdensity))
		
		self.error_slope = stats.t.ppf(0.975,self.Nstars_final-2) * math.sqrt(sigma2_slope)
		self.error_zeropoint = stats.t.ppf(0.975,self.Nstars_final-2) * math.sqrt(sigma2_int)
	
	def calculate_kendall_tau(self):
		self.kendall_tau = \
			(len(self.upper_diag_slopes[self.upper_diag_slopes>0]) - \
			len(self.upper_diag_slopes[self.upper_diag_slopes<0])) / \
			len(self.upper_diag_slopes)
			

