function fig = ebm()
% This is the machine-generated representation of a Handle Graphics object
% and its children.  Note that handle values may change when these objects
% are re-created. This may cause problems with any callbacks written to
% depend on the value of the handle at the time the object was saved.
% This problem is solved by saving the output as a FIG-file.
%
% To reopen this object, just type the name of the M-file at the MATLAB
% prompt. The M-file and its associated MAT-file must be on your path.
% 
% NOTE: certain newer features in MATLAB may not have been saved in this
% M-file due to limitations of this format, which has been superseded by
% FIG-files.  Figures which have been annotated using the plot editor tools
% are incompatible with the M-file/MAT-file format, and should be saved as
% FIG-files.

load ebm

h0 = figure('Color',[0.8 0.8 0.8], ...
	'Colormap',mat0, ...
	'FileName','ebm.fig.m', ...
	'PaperPosition',[18 180 576 432], ...
	'PaperUnits','points', ...
	'Position',[10 384 368 333], ...
	'Tag','Fig1', ...
	'ToolBar','none');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',[14 280 60 20], ...
	'String','D =', ...
	'Style','text', ...
	'Tag','StaticText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[1 1 1], ...
	'Callback',mat1, ...
	'FontSize',18, ...
	'ListboxTop',0, ...
	'Position',[100 275 60 30], ...
	'String','0.44', ...
	'Style','edit', ...
	'Tag','EditText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[1 1 1], ...
	'Callback',mat2, ...
	'FontSize',18, ...
	'ListboxTop',0, ...
	'Position',[100 233 60 30], ...
	'String','1', ...
	'Style','edit', ...
	'Tag','EditText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',[14 237 60 20], ...
	'String','Q/Qo =', ...
	'Style','text', ...
	'Tag','StaticText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[1 1 1], ...
	'Callback',mat3, ...
	'FontSize',18, ...
	'ListboxTop',0, ...
	'Position',[100 188 60 30], ...
	'String','203.3', ...
	'Style','edit', ...
	'Tag','EditText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',[14 193 60 20], ...
	'String','A =', ...
	'Style','text', ...
	'Tag','StaticText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[1 1 1], ...
	'Callback',mat4, ...
	'FontSize',18, ...
	'ListboxTop',0, ...
	'Position',[100 145 60 30], ...
	'String','2.09', ...
	'Style','edit', ...
	'Tag','EditText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',[14 150 60 20], ...
	'String','B = ', ...
	'Style','text', ...
	'Tag','StaticText1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'Callback',mat5, ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',mat6, ...
	'String','use defaults', ...
	'Tag','Pushbutton1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'Callback',mat7, ...
	'FontSize',14, ...
	'ListboxTop',0, ...
	'Position',[123.84 17.28 128.64 50.88], ...
	'String','Run EBM', ...
	'Tag','Pushbutton1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'Callback',mat8, ...
	'FontSize',12, ...
	'ListboxTop',0, ...
	'Position',[192.1136811023622 271.8408587598425 137.361281988189 32.65932578740158], ...
	'String','No Albedo Feedback', ...
	'Style','checkbox', ...
	'Tag','Checkbox1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'Callback',mat9, ...
	'FontSize',12, ...
	'ListboxTop',0, ...
	'Position',mat10, ...
	'String','Simulate Hadley Cell', ...
	'Style','checkbox', ...
	'Tag','Checkbox1');
h1 = uicontrol('Parent',h0, ...
	'Units','points', ...
	'BackgroundColor',[0.701960784313725 0.701960784313725 0.701960784313725], ...
	'Callback',mat11, ...
	'FontSize',12, ...
	'ListboxTop',0, ...
	'Position',mat12, ...
	'String','Use Cold Start', ...
	'Style','checkbox', ...
	'Tag','Checkbox1');
if nargout > 0, fig = h0; end
