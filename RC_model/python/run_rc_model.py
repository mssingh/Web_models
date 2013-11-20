#!/usr/bin/python

# Modules #########################################################################################

import time
import cgi
import os
import signal
import shutil
import subprocess 
import tempfile
import json
import multiprocessing
import threading
from statsd import statsd
import socket
import sys


# Modules specific to RC model
from mime import *
from write_input    import write_params_in,write_sounding_in
from postprocess    import output_control, get_output
from plot_model_log import plot_model_log
from s3_functions   import send_to_bucket,get_from_bucket,S3_name

# Initial setup  ###################################################################################




### Parameters for server instance ###

# Number of simultaneous model instances allowed
num_threads = 2

# max time for any given simulation (seconds)
max_simulation_time = 5*60

# Max length of queue before we kill machine
QMAX = 50

# Verbosity of log (0,0.5,1,2)
verbose = 0

# Name of log files
PIDFILE    = "../log/rc_model.pid"
LOGFILE    = "../log/rc_model_log.txt"
Q_STATFILE = "../log/queue_status.txt"
REPORTDIR  = "../log/reports/"

# Location of the tmpwatch command
TMPWATCH   = "../../tools/tmpwatch/tmpwatch"

# Name of output html template
output_opts = '../output_opts.html'

# Relative path to model executable
model_exec = '../model/rc_web'

# relative path to O3 input file
O3in = '../model/O3.in'

# Directory where each model instance will be stored
TEMPDIR = 'temp'

### Setup server instance ###

os.environ['MPLCONFIGDIR'] = './'+TEMPDIR+'/'

# Default user
DEFAULT_USER = "unknown"

# Send PID to logfile
open(PIDFILE,'w').write(str(os.getpid()))

# Make a queue to handle the model simulations
queue = multiprocessing.JoinableQueue()

# Define list/dictionary of the queued/running jobs
manager = multiprocessing.Manager()
queued_jobs = manager.dict()
queue_order = manager.list([])
running_jobs = manager.dict()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("gmail.com",80))
IPid = s.getsockname()[0]
s.close()


def LOG(x): #######################################################################################
### Function to send information to log file ###

    # Open log file in append mode 
    fp = open(LOGFILE,'a')

    
    if type(x)==dict:          # format ouput for dictionary
        for k in x:
            if not k:
                continue
            s = '  %s : %s' % (k,x[k])
            t = '%s: ' % time.ctime(time.time())
            s = t+s
            fp.write(s)
            print s
    #if type(x)==type('str'):
    else:                      # format output for string
        t = '%s: ' % time.ctime(time.time())
        x = t+x
        fp.write(x)
        fp.write('\n')
        print x

    sys.stdout.flush()
    fp.flush()
    fp.close()


def scheduled_tasks(day_num,schedule_time):
   """ Perform the daily scheduled tasks"""

   LOG('=== Running scheduled tasks')

   # Monthly tasks
   if day_num ==1:
      # Pick a time in last month 
      last_month = time.localtime(schedule_time-86400)

      # Figure out month and year strings
      the_month = time.strftime("%b",last_month)
      the_year = time.strftime("%Y",last_month)
   
      # move the log file
      report_file = REPORTDIR+the_year+'_'+the_month+'_log.txt'
      subprocess.call(['mv',LOGFILE,report_file])
 
      # Start a new log file
      LOG('=== Welcome to the month of '+the_month)    

      # Make sure we don't lose any of this months logs
      lfile=open(LOGFILE,"a")
      rfile=open(report_file)

      for line in rfile:
         if the_month in line:
            lfile.write(line)

      lfile.close()
      rfile.close()
 

   # Clean the temp directory
   ret = subprocess.call([TMPWATCH,'1',TEMPDIR])

   # Update the bar chart
   plot_model_log(LOGFILE,REPORTDIR,day_num)

   # Schedule daily tasks for tomorrow 
   schedule_daily_tasks()


def schedule_daily_tasks():
   """Schedule tasks for 01:00UTC"""

   current_time = time.localtime(time.time())
   the_date = time.strftime("%Y %m %d",current_time)
   the_day = int(time.strftime("%d",current_time))

   schedule_time = time.mktime(time.strptime(the_date,"%Y %m %d"))+86400+3600
   #schedule_time = time.time()+7
   threading.Timer(schedule_time-time.time(), scheduled_tasks, [the_day,schedule_time]).start()

class model_daemon(multiprocessing.Process): #############################################################
##### CLASS: Run queued jobs ###

    """Threaded RC model runner"""



    #----------------------------------------------------------------------
    def __init__(self, queue,queued_jobs,queue_order,running_jobs):
        multiprocessing.Process.__init__(self)
        self.queue = queue
        self.queued_jobs = queued_jobs
        self.queue_order = queue_order
        self.running_jobs = running_jobs

    #----------------------------------------------------------------------
    def run(self):
        while True:
            # gets the simulation parameters from the queue
            [dirname,submit_time,days,s3_file] = self.queue.get()

 
            # Calculate queue wait time
            wait_time = time.time()-submit_time


            # Log the wait time
            LOG('run: wait time: '+dirname+': '+str(wait_time))
            statsd.histogram('RC_model.queue_time',wait_time,tags=[IPid])
 
            # Initialize the running time
            run_time = time.time()

            # Run the simulation
            return_code = self.run_model(dirname)

            # send a signal to the queue that the job is done
            self.queue.task_done()


            # Calculate the running time per day of simulation
            run_time = (time.time() - run_time)/float(days)

            if return_code == 0:
               LOG('run: run time: '+dirname+': '+str(run_time))
               statsd.histogram('RC_model.run_time',run_time,tags=[IPid])

            # Note that result is about to be cached
               with open(dirname+'/log.out', 'w') as f:
      	  	  f.write('cached')

            # Send output to the cache
            if s3_file != '':
               send_to_bucket(s3_file,dirname)




    #----------------------------------------------------------------------
    def run_model(self,dirname):
        """"""
       
        json_output = {}

        # Extract directory name from form
        #dirname = form["dirname"].value
        json_output['dirname'] = dirname

        if self.queued_jobs[dirname] == 'run':

           # Remove from queued jobs
           del self.queued_jobs[dirname]
           self.queue_order.pop(0)
           
           # Run the model binary in a subprocess - use timeout to prevent hanging
           run_obj = subprocess.Popen(["timeout",str(max_simulation_time),model_exec,dirname], \
                    stderr=None, stdout=None, preexec_fn=os.setsid	)

           self.running_jobs[dirname] = run_obj.pid


           # wait for process to exit
           run_obj.wait()
           # Python 3.3 has native timeout - for now use shell function "timeout"
           #run_obj.wait(timeout=max_simulation_time)

           return_code = run_obj.returncode
           del self.running_jobs[dirname]

           
           # If process timed out note this in logfile
           if run_obj.returncode == 124:
               try:
                  with open(dirname+'/log.out', 'w') as f:
                     f.write('timeout')
               except:
                  LOG('>> Error: Missing log file on timeout - '+dirname)
                  statsd.increment('RC_model.error',tags=[IPid,'logfilemissing'])
 
               return return_code

           elif run_obj.returncode > 0:

               LOG('run: Model exit with code '+str(run_obj.returncode)+' - '+dirname)
               statsd.increment('RC_model.error',tags=[IPid,'exit:'+str(run_obj.returncode)])
               try:
                  with open(dirname+'/log.out', 'w') as f:
                     f.write('exit '+str(run_obj.returncode))
               except:
                  LOG('>> Error: Missing log file on crash - '+dirname)
                  statsd.incremenr('RC_model.error',tags=[IPid,'logfilemissing'])
              
               return return_code

 
        else:
           del self.queued_jobs[dirname]
           self.queue_order.pop(0)
           return_code = -1;

	   return return_code


	# Check that there is output
        if ( not os.path.isfile(dirname+'/sounding.out') ):

                if verbose > 0: LOG('Clean: model terminated by user or crashed')
                try:
                   shutil.rmtree(dirname)
                   if verbose >0: LOG('Clean: Directory removed')
                except:
                   if verbose > 0: LOG('Clean: Directory cannot be removed')

                return return_code
        	
        
        # Plot output 
        form = {}
        form["plot_opt"] = "time_sst"
        json_output = output_control(form,dirname,json_output)


        
        # tell client we are done
        with open(dirname+'/log.out', 'w') as f:
           f.write('finished')
        

        return return_code


def replot_sim(form, path, queue,user): ################################################################
### Function to call when client asks to replot data from simulation ###

    '''
    This function replots data from a simulation
    '''

    # Initialize JSON output structure ----------------------------
    json_output = {}
    json_output['html'] = ''           # html to display
    json_output['status'] = 'queued'   # model status
    json_output['alert'] = ''          # error message to print

    if 'dirname' in form:
        dirname = form['dirname'].value
    else:
        dirname = ''

    if verbose > 0: LOG('Replot: '+user+': '+dirname)
    if verbose > 1: LOG("Inputs: %s" % dict((k,form[k].value) for k in form))

    json_output = output_control(form,dirname,json_output)
    return json.dumps(json_output,indent=1)



def submit_sim(form, path, queue,user): ################################################################
### Function to submit simulation ###

# This is what we do when the browser posts some data to the server

        '''
        This function submits a simulation to be run.
        '''
        print "form=%s" % dict((k,form[k].value) for k in form)
        # Put some info in the LOG file -------------------------------
        days = form['days'].value
        LOG('Submit simulation: %s: %s, length: %s days' % (user,form['dirname'].value,days)) 
        statsd.increment('RC_model.submit',tags=[IPid])
         
        if verbose > 1:
           LOG("form=%s" % dict((k,form[k].value) for k in form))
        

        # Initialize JSON output structure ----------------------------
        json_output = {}
        json_output['html'] = ''           # html to display
        json_output['status'] = 'queued'   # model status
        json_output['alert'] = ''          # error message to print

 
        # Make directory for input/output -----------------------------
        
        # if dirname exists try to use this directory
        dirname = form["dirname"].value
        
        # Add dirname to JSON output
        json_output['dirname'] = dirname



        # Check to see if directory still exists
       	if not os.path.isdir(dirname):
        
       		if "restart" in form:
       			# Trying to restart but the directory has vanished
                        json_output['html']  ="<html><h2>Restart error</h2>"
                        json_output['html'] +="<h4>Cannot find previous output: Your session has probably expired. </h4>"
                        json_output['html'] +="<p>If you leave the model idle for longer than 20 minutes its output may be cleaned up,"
                        json_output['html'] += "preventing you from restarting the model from the end of the simulation."

                        json_output['alert']  ="Restart error: Cannot find previous output."
			json_output['alert'] +="\nYour session has probably expired.\n\n"
                        json_output['alert'] +="If you leave the model idle for longer than 20 minutes its output may be cleaned up,"
                        json_output['alert'] +=" preventing you from restarting the model from the end of the simulation"

			return json.dumps(json_output,indent=1)

       		else:
       			# Can't find directory, so create a new unique directory 
      			dirname = tempfile.mkdtemp(dir=TEMPDIR)
                        form["dirname"].value = dirname
        

        # Add dirname to JSON output
        json_output['dirname'] = dirname

        # If restart move pforile.out to profile.old
        if ( os.path.isfile(dirname+'/profile.out') ): 
                os.rename(dirname+'/profile.out',dirname+'/profile.old')

        # Set name for s3 storage of cached results
        s3_file = S3_name(form)

        # Attempt to obtain output from cache
        if 'restart' not in form:
           retval = get_from_bucket(s3_file,dirname)
           if retval == 0:
              json_output['html'] = '<br><br><br><center><h3>Retrieving cached results</h3><br><br><h2>Please Wait<h2></center><br>'
              form = {}
              form["plot_opt"] = "time_sst"
              json_output = output_control(form,dirname,json_output)
              LOG('run: Returning cached result')
              statsd.increment('RC_model.cached',tags=[IPid])
              return json.dumps(json_output,indent=1)

        
	# Write inputs for model ------------------------------
        
        # write the 'params.in' file
        err = write_params_in(form,dirname)
        
        
        # If server-side form validation failed write error
        if err['err'] == 'fatal':
                json_output['html']  = '<html><h2>Input error</h2>'
                json_output['html'] += 'The input value for: <b>"'+err['var']+'"</b> produced an error. <br>'
                json_output['html'] += 'This input should be of type: <b>'+err['type']
                json_output['html'] += ' </b> in the range <b> ['+err['min']+','+err['max']+'] </b><br>'
                json_output['html'] += 'The value given was: <b>"'+err['value']+'"</b> <br> </html>'
			
		json_output['alert']  = "Input error: Invalid input for "+err['var']
                json_output['alert'] += "\n\nInput should be of type: "
                json_output['alert'] += err['type']+" in the range "+err['min']+" - "+err['max']
                json_output['alert'] += "\nValue given was: "+err['value']

                if verbose > 0: LOG('>> Error: Input error - '+dirname)
                if verbose > 1:
                   LOG('>> Var:  '+err['var'])
                   LOG('>> Type: '+err['type'])
                   LOG('>> min:  '+err['min'])
                   LOG('>> max:  '+err['max'])
                   LOG('>> val:  '+err['val'])

                return json.dumps(json_output,indent=1)
	
       	# write the 'sounding in' file
        err_sounding = write_sounding_in(form,dirname,O3in)

        # If server-side form validation failed write error
        if err['err'] == 'fatal':
                json_output['html']  = '<html><h2>Input error</h2>'
                json_output['html'] += 'The input value for: <b>"'+err['var']+'"</b> produced an error. <br>'
                json_output['html'] += 'This input should be of type: <b>'+err['type']
                json_output['html'] += ' </b> in the range <b> ['+err['min']+','+err['max']+'] </b><br>'
                json_output['html'] += 'The value given was: <b>"'+err['value']+'"</b> <br> </html>'
			
		json_output['alert']  = "Input error: Invalid input for "+err['var']
                json_output['alert'] += "\n\nInput should be of type: "
                json_output['alert'] += err['type']+" in the range "+err['min']+" - "+err['max']
                json_output['alert'] += "\nValue given was: "+err['value']

                if verbose > 0: LOG('>> Error: Fatal - '+dirname)
                return json.dumps(json_output,indent=1)




       	# Check input files exist
        if ( not os.path.isfile(dirname+'/params.in') ) or ( not os.path.isfile(dirname+'/sounding.in') ): 
       		json_output['html'] = '<html><h2>Input error</h2>'
       		json_output['html'] +='<p>There was a problem writing the required input files to the RC model. '
                json_output['html'] +='Please go back and try running again. <\html>' 

       		json_output['alert'] = 'Input error: Cannot find input files'
       		json_output['alert'] +='\n\nThere was a problem writing the required input files to the RC model.'
                json_output['alert'] +='Please go back and try running again. <\html>' 

                LOG('>> Error: Could not create input file')
                statsd.increment('RC_model.error',tags=[IPid,'createinputfile'])
		return json.dumps(json_output,indent=1)
        


	
       	# Put run in queue ------------------------------------
                 
        # Write status
      	with open(dirname+'/log.out', 'w') as f:
      		f.write('enqueued')


        # Put in queue 
        queued_jobs[dirname] = 'run' 
        queue_order.append(dirname)
        statsd.increment('submission')
        submit_time = time.time()
        queue.put([dirname,submit_time,days,s3_file])             
        json_output['html'] = '<br><br><br><center><h3>Your job is in the queue</h3><br><br><h2>Please Wait<h2></center><br>'



        # Write the model and queue status
        write_queue_status()

        return json.dumps(json_output,indent=1)
              


def enquire_sim(form,path,queue,user): #################################################################
### Function called when client asks server on progress of simulation ###

    '''
    This function returns the status of a simulation
    '''
    # Initialize JSON output ------------------------------------------
    json_output = {}
    json_output['html'] = ''    # html to display
    json_output['status'] = ''  # model status
    json_output['alert'] = ''   # Error output



    # Get the name of the temporary directory
    dirname = form["dirname"].value

    # Read the model status from the log file ------------------------
    model_log = dirname+'/log.out' 
   
    if verbose > 0: LOG('Enquire: '+user+': '+dirname)
    
    if os.path.exists(model_log):   # Look for model log and read
	with open(model_log, 'r') as fin:
            model_status = fin.read()

    else:		# Log does not exist model must have crashed
        model_status = 'undefined'
        json_output['status'] = 'undefined';
        json_output['html']   = '<h2>Model Error</h2>';
        json_output['html']  += 'The model has crashed. Click Run model to rerun the simulation.';
        json_output['alert']  = 'Model Error\n\n';
        json_output['alert'] += 'The model has crashed.\n\n'
        json_output['alert'] += 'If this problem persists please email mssingh@mit.edu,'
        json_output['alert'] += ' including as much detail on the problem as possible.';

        if verbose > 0: LOG('>> Error: Fatal - '+dirname)


    # Return the status to the client --------------------------------

    try: 	# Try to convert to percentage
        model_status = float(model_status)*100
        json_output['status'] = 'running'
        json_output['progress'] = model_status
        json_output['html'] = '<br><br><br><center><h3>Model is running</h3><br><br><h2>Please Wait<h2></center><br>'

    except:	# If not number find out if queued or finished

        # Model is queued ~~~~~~~~~~~~~~~~~~~~
        if model_status == 'enqueued':

           json_output['status']   = 'queued' 
           json_output['progress'] = 'false' 

           json_output['html']  = '<br><br><br><center><h3>Your job is in the queue</h3>'
           try:
              queue_num = queue_order.index(dirname)+1
              json_output['html'] += '<br><br><h2>Your job is number '+str(queue_num)+' in the queue</h2></center><br>'
           except:
              json_output['html'] += '<br><br><h2>Please Wait</h2></center><br>'

        # Model is finished ~~~~~~~~~~~~~~~~~~
        elif  model_status == 'finished' or model_status == 'cached':

           json_output['status'] = 'done'
           fig_file = dirname+'/plot1.png'

	   if os.path.isfile(fig_file):
        	image_code =  "<img id=plot src=/rc/"+fig_file+" alt=\"RC model output\" width=\"600\" height=\"450\" />"
	   else:
        	image_code =  '<html><h2>Plotting error</h2>'
                image_code += '<p>There was an error in creating the plot you asked for. <br>'
                image_code += 'You can try plotting something else, or rerun the simulation.'
       

           # Read some key numbers and from the output files
           table_vals      = get_output(dirname+'/topbar.out')
           table_vals.extend(get_output(dirname+'/botbar.out'))
           table_vals.extend(get_output(dirname+'/lwbar.out'))
           table_vals.extend(get_output(dirname+'/swbar.out'))
           table_vals.extend(get_output(dirname+'/shfbar.out'))
           table_vals.extend(get_output(dirname+'/sstbar.out'))


           
           # Read the replotting form html
           with open(output_opts, 'r') as fin:
        	html_file = fin.read()
        
        
	   # Print the plot
	   html_file = html_file.replace('<!-- image goes here -->',image_code)

           # See if we can make comparison plots
	   if ( os.path.isfile(dirname+'/profile.old') ): 
	      html_file = html_file.replace('<!--DIFF','')
	      html_file = html_file.replace('DIFF-->','')
           

	   # Add the average values to the table (Upward fluxes are positive)
	   html_file = html_file.replace('#FNTOA#',"%7.1f" % -float(table_vals[0][0]))
	   html_file = html_file.replace('#LWTOA#',"%7.1f" % -float(table_vals[2][0]))
	   html_file = html_file.replace('#LWSFC#',"%7.1f" % -float(table_vals[3][0]))
	   html_file = html_file.replace('#SWTOA#',"%7.1f" % -float(table_vals[4][0]))
	   html_file = html_file.replace('#SWSFC#',"%7.1f" % -float(table_vals[5][0]))
	   html_file = html_file.replace('#SHSFC#',"%7.1f" % float(table_vals[6][0]))
	   html_file = html_file.replace('#LHSFC#',"%7.1f" % float(table_vals[7][0]))
	   html_file = html_file.replace('##SST##',"%7.1f" % float(table_vals[8][0]))
        
           # Make sure the new form knows where the output lives so we can restart
	   html_file = html_file.replace('dirname" value="','dirname" value="'+dirname)
       

           # Log that model completed succesfully
           LOG('run: success: '+dirname)
           statsd.increment('RC_model.complete',tags=[IPid])
 
	   # print the html to file
	   json_output['html'] =  html_file

   

        # Model timed out ~~~~~~~~~~~~~~~~~~
        elif model_status =='timeout':
          json_output['alert']  = 'Simulation timed out\n\n ' 
          json_output['alert'] += 'The simulation you requested is taking too long.\n'
          json_output['alert'] += 'This may be because you have requested a job that is too intensive, or there is a problem with the server.\n'
          json_output['alert'] += 'Try shortening the length of the simulation and try again.'
          json_output['html'] = '<br><br><br><center><h3>Simulation timed out</h3><br><br>'
          json_output['html'] += '<h2>click "Run model" to start again<h2></center><br>'

          LOG('>> Error: Timeout - '+dirname)
          statsd.increment('RC_model.error',tags=[IPid,'timeout'])

        # Model crashed  ~~~~~~~~~~~~~~~~~~
        elif model_status.startswith('exit'):
          json_output['alert']  = 'Simulation crashed!\n\n ' 
          json_output['alert'] += 'The simulation you requested could not be completed. Possible reasons may be:\n'
          json_output['alert'] += ' - The initial condition is too far from equilibrium. Try changing the initial SST.\n'
          json_output['alert'] += ' - The parameters are too unrealistic. Try changing them to be closer to the defaults.'
          json_output['html'] = '<br><br><br><center><h3>Simulation could not be completed</h3><br><br>'
          json_output['html'] += '<h2>click "Run model" to start again<h2></center><br>'

          if verbose > 0: LOG('>> Error: Crash - '+dirname)
        # Something else happened ~~~~~~~~~~~
        elif model_status =='kill':
          json_output['html'] = '<br><br><br><center><h3>Unknown fatal error occured</h3><br><br>'
          if verbose > 0: LOG('>> Error: Fatal - '+dirname)
 
        else: 
          json_output['html'] = '<br><br><br><center><h3>Unknown fatal error occured</h3><br><br>'
          if verbose > 0: LOG('>> Error: Fatal - '+dirname)
 
    
    return json.dumps(json_output,indent=1)


def clean_sim(form,path,queue,user): ###################################################################
### Function called when client wants to delete simulation and cleanup ###

    '''
    This function stops the active simulation and cleans up its output
    '''
    
    # Initialize JSON output structure ----------------------------
    json_output = {}
    json_output['html'] = ''           # html to display
    json_output['alert'] = ''          # error message to print




    if 'dirname' in form:
       dirname = form['dirname'].value
    else:
       dirname = 'nn'

    if verbose > 0: LOG("Clean: "+user+': '+dirname)
    if verbose > 1:
       LOG(running_jobs)
       LOG(queued_jobs)

    if dirname == '' or dirname == 'n': 	 # No cleanup required

       if verbose > 1: LOG("Clean: no cleaning up to be done: "+dirname)
       json_output['status'] = 'undefined';
       return json.dumps(json_output,indent=1)

    
    if dirname in running_jobs:			 # Model is running - need to stop

         jobid = running_jobs[dirname]
         os.killpg(jobid, signal.SIGTERM)
         LOG('run: killing simulation: '+dirname)
         json_output['status'] = 'kill';

         # Note that simulation killed in log
         try:
            with open(dirname+'/log.out', 'w') as f:
                f.write('kill')
         except:
                 if verbose > 0: LOG('Error: clean - Missing log file')


    if dirname in queued_jobs:			 # simulation is queued - remove from queue
            queued_jobs[dirname] = 'kill'
            json_output['status'] = 'kill';

            LOG('run: removing from queue: '+dirname)
            # note that simulation killed in log
            with open(dirname+'/log.out', 'w') as f:
            	f.write('kill')

    
    if "leaving" in form:			 # Client is leaving delete their temp directory 

            try:
              shutil.rmtree(dirname)
            except:
              if verbose > 0: LOG("Can't find "+dirname+": probably already cleaned")


    return json.dumps(json_output,indent=1)

def get_health(path, queue): ##############################################################
### Function called when client asks for health of queue ###

    '''
    This function returns the queue status files.
    '''
    write_queue_status()
  
    if queue.qsize() > QMAX:
       return 'ERROR: 502: Queue too large','502 Bad Gateway'
 
    if os.path.exists(Q_STATFILE):

       return  open(Q_STATFILE).read(),'200 OK'

    else:
       return 'ERROR: No queue status file','200 OK'


def get_textfile(form, path, queue,user): ##############################################################
### Function called when client asks for text output ###

    '''
    This function returns text files.
    '''

    textfile = form["textfile"].value
   
    if verbose > 0: LOG('Textfile: '+user+': '+textfile)

 
    if os.path.exists(textfile):

       return  open(textfile).read()

    else:
       return 'could not find text output'

def get_figurefile(form,path,queue,user): ##############################################################
### Function called when client asks for the figure ###

    '''
    This function returns figure files.
    '''
    if verbose > 0: LOG('Figure: '+user+': '+path)

    

    if not path.startswith(TEMPDIR):
       
       if verbose > 0: LOG('>> Error: Unknown file request - '+path)
       return 'Unknown file request'
       

    if os.path.exists(path):
       if path.endswith('png'):
          return PNG(open(path).read())
       else:
          return HTML(open(path).read())

    if verbose > 0: LOG('>> Error: Cannot find requested output - '+path)
    return 'Cannot find requested output'


###################################################################################
# wsgi interface


# Entry point
def application(env, start_response):


        tic = time.time()
	
	method = env['REQUEST_METHOD']
	path = env.get('PATH_INFO', '').lstrip('/')
	data = None
	
	#sslcert = env.get('HTTP_SSL_CLIENT_S_DN','')	# username from SSL cert
        user = DEFAULT_USER
	#if sslcert:
        #	user = sslcert.rsplit('emailAddress=',1)[-1]


        # Log the request
        if verbose > 1:	
	   LOG('-' * 60)
	   LOG(method)
	   LOG('user = %s' % user)
	   LOG('path = %s' % path)


        # set the response
        response = '200 OK'

        # Get the data from the request
	data = cgi.FieldStorage(fp=env['wsgi.input'], environ=env.copy(), keep_blank_values=True)

        # Decide what client is asking for ########################################
	if method=='POST': 			# POST method

             if "replot" in data: 	# Client is replotting some data

                 ret = replot_sim(data,path,queue,user)

             else: 			# Client is submitting a simulation to be run     

                 ret = submit_sim(data,path,queue,user)

	else:					# GET method

             if "clean" in data: 	# Client wants to stop simulation and clean it up
                 ret = clean_sim(data,path,queue,user)

             elif "dirname" in data: 	# Client is asking for simulation progress  
                 ret = enquire_sim(data,path,queue,user)
 
             elif "health" in path:
                 ret,response = get_health(path,queue)

             elif "textfile" in data: 	# Client wants text data
                 ret = get_textfile(data,path,queue,user)

             else:                 	# Client is asking for figure file
                 ret = get_figurefile(data,path,queue,user)
		
        if isinstance(ret, webobj):	# see mime.py
                mime = ret.mime
        else:
                mime = "text/plain"

        start_response(response, [('Content-Type', mime)])
        
        # Write the model and queue status
        write_queue_status()

        if verbose > 1: LOG("done at %s" % time.ctime(time.time()))

        if verbose > 0.7: LOG("=== time taken: "+str((time.time()-tic)*1000)+" ms")
 
        # Send the IP address if sending a json object
        try:
           ret['IPaddress'] = IPid
        except:
           pass

        return [str(ret)]



def write_queue_status(): #########################################################################
### Function to write the wueue status to the log ###

       # Make sure we haven't lost any threads

       running_procs = multiprocessing.active_children()

       alivethread = len(running_procs)-1
       if  alivethread < num_threads:

            LOG("Found only "+str(alivethread)+" model thread(s). Restarting broken thread(s).")

            for i in range(alivethread,num_threads):
               t = model_daemon(queue,queued_jobs,queue_order,running_jobs)
               t.daemon = True
               t.start()


       alivethread = len(multiprocessing.active_children())-1
       with open(Q_STATFILE, 'w') as f:
            f.write('-----------------------------------\n')
            f.write('Time: '+time.ctime(time.time())+'\n')
            f.write('Number of model threads:   '+str(num_threads)+'\n')
            f.write('Number of working threads: '+str(alivethread)+'\n\n')
            f.write('Number of server threads:  '+'2'+'\n\n')
            f.write('Running jobs:\n')

            for key in running_jobs.keys(): f.write('    '+str(key)+' : '+str(running_jobs.get(key))+'\n')
            f.write('\n')
            f.write('Queued jobs:\n')

            for key in queued_jobs.keys(): f.write('    '+str(key)+' : '+str(queued_jobs.get(key))+'\n')

            f.write('\n')

 
       statsd.gauge('RC_model.threads',num_threads,tags=[IPid])
       statsd.gauge('RC_model.working_threads',alivethread,tags=[IPid])
       statsd.gauge('RC_model.queued_jobs',len(queued_jobs),tags=[IPid])
       statsd.gauge('RC_model.running_jobs',len(running_jobs),tags=[IPid])



#--------------------

host = 'localhost'
#PORT = 9004	# ichuang
PORT = 9003	# marty

def runserver(): ##################################################################################


        num_CPUs = multiprocessing.cpu_count()

	LOG('==================================================')
	LOG('=== Starting Radiative-convective model server ===')
        LOG('===                                               ')
	LOG('=== Using %s threads for RC model                 ' % str(num_threads))
	LOG('=== On %s CPUs                                    ' % str(num_CPUs))
	LOG('===                                               ')
	LOG('=== Max simulation time: %s seconds               ' % str(max_simulation_time))
	LOG('==================================================')



	# create a thread pool and give them a queue
	for i in range(num_threads):
	    t = model_daemon(queue,queued_jobs,queue_order,running_jobs)
	    t.start()


        # schedule the daily cleanup tasks
        schedule_daily_tasks()

        # Write the queue status to a file
        write_queue_status()

        # Start server
	from wsgiref.simple_server import make_server
	srv = make_server(host, PORT, application)
	srv.serve_forever()
   
	
if __name__ == '__main__':
	runserver()
