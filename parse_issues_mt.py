#!/usr/bin/python
import re,urllib2,Queue,threading,html2text
from types import *

"""
Parse positions given a politician's issue page html from ontheissues.org
"""

class Threader(threading.Thread):
	def __init__(self,id,req_queue):
		threading.Thread.__init__(self,name="Thread-%d" % (id,))	
		self.req_queue = req_queue
	def run(self):
		while 1:
			req = self.req_queue.get()
			if req is None:
				break
			else:
				# here value_one is the position title, value_two is the reference string
				(value_one,value_two,value_three,resp_queue) = req
				result_one = value_one
				result_two = parse_ref(value_two.group(1),value_one,value_three)
				result_three = value_three
				resp_queue.put( (result_one,result_two,result_three) )
		
def getPrimarySource(url):
	"""
	Input: url string to one of the ontheissues.org secondary source/cit pages
	Returns: url string to the primary source page linked to by the ontheissues.org source/cit page
	"""
	u = urllib2.urlopen(url)
	html = u.read()
	
	mat = re.search("<h2>[a-zA-Z ]*?<a href='(.+?)'",html)
	
	try:
		return mat.group(1)
	except:
		return url

def parse_link(linkhtml):
	"""
	Input: link's anchor sans the outermost enclosing carats
	Returns: (title, URL)
	"""
	link_title = linkhtml[linkhtml.index(">")+1:linkhtml.index("<")]

	match_url = re.search("href=['\"](.+?)['\"]",linkhtml)
	if (match_url):
		if (match_url.group(1)).find("ontheissues.org") < 0:
			link_url = match_url.group(1)
		else:
			link_url = getPrimarySource(match_url.group(1))
	else:
		link_url = "./no_link_found"
		
	return (link_title,link_url)

def parse_ref(refhtml,position_name,position_body):
	"""
	Input: html reference string
	Returns: array of dictionaries of reference links
	"""
	reftype = re.match("([a-zA-Z]+?):",refhtml)

	# reformat local links		
	refhtml = refhtml.replace("../","http://house.ontheissues.org/")
	
	# remove leading "Source: " or "Reference: "
	refhtml = refhtml[refhtml.index(":")+2:]
	
	refs_array = []
	refs = refhtml.split("; ")
	ext_desc = ""
	
	# to throw away the long useless name in e.g. 
	# Reference: Stem Cell Research Enhancement Act; Bill S.5 & H.R.3 ; vote number 2007-127  on Apr 11, 2007 
	if len(refs) > 1 and refs[0].find("<a") < 0:
		ext_desc = refs[0]
		del refs[0]
	
	# parse each reference in the ref string
	for r in refs:
		ref_dict = {}
		try:
			# there is an anchor
			linkstart = r.index("<a")
			linkend = r.index("a>")+1
		except:
			# there is no anchor
			linkstart = len(r)
			linkend = 0
			
		ref_dict['title'] = r[0:linkstart]
		
		# get reference type
		if re.match("Voted",position_name):
			if ref_dict['title'] == 'Bill ':
				ref_dict['type'] = 'bill'
				ref_dict['title'] = ext_desc
			elif ref_dict['title'] == 'vote number ':
				ref_dict['type'] = 'vote'
				ref_dict['title'] = ext_desc
			else:
				ref_dict['type'] = 'legislative-unknown'
		elif re.match("Rated",position_name):
			ref_dict['type'] = 'rating'
		elif re.search("[Cc]o-sponsored",position_body):
			ref_dict['type'] = 'cosponsor'
		elif re.match("Sponsored",position_name) or re.search("[Ii]ntroduced",position_body):
			ref_dict['type'] = 'sponsor'
		else:
			ref_dict['type'] = 'unknown'
		
		#if (len(r[0:linkstart]) > len(ext_desc)) else ext_desc
		
		# if there was an anchor
		if linkstart < linkend:
			(ref_link_title,ref_url) = parse_link(r[linkstart+1:linkend])
			ref_dict['link-text'] = ref_link_title
			ref_dict['link-url'] = ref_url

		# get the date
		date_match = re.search("([A-Z][a-z][a-z] [0-9]{1,2}, [0-9]{4})$",r)
		if (date_match):
			ref_dict['date'] = date_match.group(1)
			ref_dict['title'] = ref_dict['title'].replace(ref_dict['date'],"")
		else:
			ref_dict['date'] = 'unknown'
		
		# store this reference
		refs_array.append(ref_dict)
	
	# return all references found in the ref string
	return refs_array
	
def scrape_positions(html,numThreads=1):
	"""
	Input: html string (contents of a position page)
	Returns: array of dictionaries, [{"position":<string>,"ref":<array of dicts>}, ... ] 
	"""

	html = html.replace("\r\n","")
	posns = html.split('<h3><center>')
	
	# get name
	matchName = re.search("<TITLE> (.+?) on (.+)",posns[0])
	del posns[0]
	
	numPosns = len(posns)
	
	req_queue = Queue.Queue()
	resp_queue = Queue.Queue()
	names = []
	reftexts = []
	kinds = []
	positions = []
	bodies = []

	# scrape out position names, reference strings
	for pos in posns:
		matchName = re.match("([^<]+)",pos)
		names.append(matchName.group(1))
		reftext = re.search('SIZE=1>(.+?)</center></font>',pos)
		reftexts.append(reftext)
		body = re.search('</center>(.+?)<center>',pos)
		try:
			bodytext = html2text.html2text(body.group(1))
		except:
			bodytext = "HTML " + body.group(1)
		bodies.append(bodytext)
		
	# start threads
	for tid in range(numThreads):
		Threader(tid,req_queue).start()

	# enqueue jobs for threads
	for i in range(numPosns):
		req_queue.put( (names.pop(),reftexts.pop(),bodies.pop(),resp_queue) )
	
	# enqueue stop signals in threads
	for i in range(numThreads):
		req_queue.put(None)
		
	# dequeue results into an array
	for _ in range(numPosns):
		(name,refs_array,body) = resp_queue.get()
		yield {"position":name,"body":body,"refs": refs_array}
