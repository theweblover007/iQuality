# coding: utf-8
# Copyright (C) 2012-2015 Itay Brandes

'''
Module for project's Web Services that are not lyrics or links grabbing.
'''

import sys
import traceback
import urllib
import urllib2
import httplib, xml.dom.minidom
import gzip
from xml.parsers.expat import ExpatError
import re
import json
from cStringIO import StringIO
from collections import OrderedDict

from bs4 import BeautifulSoup

sys.path.append('..') # for project top-level modules
import Config; config = Config.config
from logger import log
import utils

__all__ = ['spell_fix', 'googleImageSearch', 'google_autocomplete', 'parse_billboard', 'parse_uktop40',
			'parse_glgltz', 'parse_chartscoil', 'get_currentusers', 'get_newestversion', 'inform_esky_update',
			'get_components_data', 'get_packages_data']
			
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def spell_fix(s):
	"Uses google website to fix spelling"
	if log:
		log.debug("Checking spell suggestions for '%s'..." % s)
		
	q = s.lower().strip()
	if isinstance(q, unicode):
		q = q.encode('utf-8')
	url = "http://www.google.com/search?q=" + urllib.quote(q)

	request = urllib2.Request(url)
	request.add_header('Accept-encoding', 'gzip')
	request.add_header('User-Agent','Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_3) AppleWebKit/535.20 (KHTML, like Gecko) Chrome/19.0.1036.7 Safari/535.20')
	data = urllib2.urlopen(request).read()
	if data[:2] == '\x1f\x8b': # data is gzipped!
		buf = StringIO(data)
		f = gzip.GzipFile(fileobj=buf)
		data = f.read()
	
	soup = BeautifulSoup(data)
	ans = soup.find('a', attrs={'class' : 'spell'})
	
	if ans and ans.text and ans.text != q:
		if log:
			log.debug("Suggestion was accepted: %s --> %s." % (s, ans.text))
		return ans.text
	else:
		if log:
			log.debug("No suggestions were accepted.")
		return s

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def old_spell_fix(s):
	"Uses google API to fix spelling"
	data = u"""
	<spellrequest textalreadyclipped="0" ignoredups="1" ignoredigits="1" ignoreallcaps="0">
	<text>%s</text>
	</spellrequest>
	"""
	data = data % s
	data_octets = data.encode('utf-8')
	new_s = s
	
	if log:
		log.debug("Checking spell suggestions for '%s'..." % s)
	
	if utils.isHebrew(s):
		log.debug("Search string is hebrew. Skipping on spell checking...")
		return s
	
	con = httplib.HTTPConnection("www.google.com", timeout=config.webservices_timeout)
	con.request("POST", "/tbproxy/spell?lang=en", data_octets, {'content-type': 'text/xml; charset=utf-8'})
	response = con.getresponse().read()
	
	if log:
		log.debug("Response: %s" % response)
	
	try:
		dom = xml.dom.minidom.parseString(response)
		dom_data = dom.getElementsByTagName('spellresult')[0]
	except ExpatError:
		log.warning('spell_fix failed: ExpatError.')
		return s

	for node in dom_data.childNodes:
		att_o = int(node.attributes.item(2).value) # The offset from the start of the text of the word
		att_l = int(node.attributes.item(1).value) # Length of misspelled word
		att_s = int(node.attributes.item(0).value) # Confidence of the suggestion
		if not node.firstChild: # no suggestions
			return s
		text = node.firstChild.data.split("\t")[0]
		
		# print "%s --> %s (s: %d)" % (s[att_o:att_o+att_l], text, att_s)
		if att_s: # if suggestion is confident
			new_s = new_s.replace(s[att_o:att_o+att_l], text)
	
	if log:
		if s == new_s:
			log.debug("No suggestions were accepted.")
		else:
			log.debug("Suggestions were accepted: %s --> %s." % (s, new_s))
		
	return new_s
	
@utils.decorators.retry(Exception, logger=log)
def google_autocomplete(s):
	"Uses google autocomplete API"
	url = "http://suggestqueries.google.com/complete/search?client=firefox&q=%s" % urllib2.quote(s.encode("utf8"))
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	response = obj.read()
	data = json.loads(response)[1]
	
	BLACKLIST_WORDS = ['twitter', 'lyrics', 'tickets', 'facebook', 'retire', 'youtube', 'wiki', 'news', 'instagram', 'tattoos', 'tabs', 'chords',
						u'ליריקה', u'מילים לשירים']
	
	data = [x for x in data if not any(map(x.endswith, BLACKLIST_WORDS))]
	# print data
	
	return data

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def googleImageSearch(s):
	"Uses google API to image grabbing"
	s = urllib2.quote(s.encode("utf8"))
	url = "http://ajax.googleapis.com/ajax/services/search/images?v=1.0&q=%s" % s
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	json_data = obj.read()
	data = json.loads(json_data)
	if not data['responseData'] or data['responseData'] == 'null':
		return "Response %s: %s" % (data['responseStatus'], data['responseDetails'])
	
	images = [image_info['unescapedUrl'] for image_info in data['responseData']['results']]
	log.debug('Got images: %s' % str(images))
	return images

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def parse_billboard():
	"Parses the top 100 songs from billboard.com rss feed"
	url = 'http://www.billboard.com/rss/charts/hot-100'
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	response = obj.read()
	obj.close()
	
	songs = []
	soup = BeautifulSoup(response)
	for item in soup.find_all('item'):
		artist = item.artist.text.split('Featuring')[0]
		title = item.chart_item_title.text
		
		song = "%s - %s" % (artist, title)
		song = song.replace('  ', ' ')
		
		songs.append(song)

	return songs
	
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def parse_uktop40():
	"Parses the top 40 songs from uktop40.com rss feed"
	url = r'http://www.uktop40.co.uk/official_top_40.rss'
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	response = obj.read()
	obj.close()
	
	soup = BeautifulSoup(response)
	songs = [x.text for x in soup.find_all('title')][2:]
	songs = [x.split(') ', 1)[1] for x in songs]
	songs = [utils.trim_between(utils.trim_between(x), '[', ']') for x in songs]
	songs = [utils.convert_html_entities(x) for x in songs]
	songs = [x.strip() for x in songs]
	
	return songs

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def parse_glgltz():
	"Parses the top songs from glgltz"
	url = 'http://www.glgltz.co.il/1177-he/Galgalatz.aspx'
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	response = obj.read()
	soup = BeautifulSoup(response)
	
	# from PyQt4 import QtCore; import pdb; QtCore.pyqtRemoveInputHook(); pdb.set_trace()
	tags = soup.find_all('a', id=re.compile('Master_ContentPlaceHolder1_rptTabs'))
	catid = [x['catid'] for x in tags if u"המצעד הישראלי" in x.text][0]

	url = 'http://www.glgltz.co.il/Shared/Ajax/GetTophitsByCategory.aspx?FolderId=%s&amp;lang=he' % catid
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url)
	response = obj.read()

	songs = []
	soup = BeautifulSoup(response)

	for tag in soup.find_all('div', class_='hit'):
		title = tag.h4.text if tag.h4 else None
		artist = tag.span.text if tag.span else None
		
		if artist and title:
			songs.append("%s - %s" % (artist, title))
		elif artist:
			songs.append(artist)
		elif title:
			songs.append(title)
		else:
			raise RuntimeError("Could not parse glgltz hits")

	return songs
	
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def parse_chartscoil():
	"Parses the top songs from charts.co.il"
	url = r"http://www.charts.co.il/chartsvote.asp?chart=1"
	log.debug('Fetching %s...' % url)
	obj = urllib2.urlopen(url, timeout=config.webservices_timeout)
	response = obj.read()
	obj.close()
	
	l = []
	soup = BeautifulSoup(response)
	
	for link in soup.find_all('img', src=re.compile('/charts-co-il/singles-heb-pic')):
		l.append(link['alt'])
	return l

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def get_currentusers():
	"Function queries the iQuality website for the current application users counter"
	obj = urllib2.urlopen(config.online_users_counter_webpage, timeout=config.webservices_timeout)
	x = obj.read(1024)
	obj.close()
	try:
		return int(x)
	except ValueError:
		return 0

@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def get_newestversion():
	"Function queries the iQuality website for the the newest version available"
	obj = urllib2.urlopen(config.newest_version_API_webpage, timeout=config.webservices_timeout)
	x = obj.read(1024)
	obj.close()
	try:
		return float(x)
	except ValueError:
		return 0
		
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def inform_esky_update(fn, v):
	obj = urllib2.urlopen(config.inform_esky_update_webpage % (fn, v), timeout=config.webservices_timeout)
	x = obj.read(1024)
	obj.close()
	
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def get_components_data():
	"Function queries the iQuality website for components json data"
	try:
		obj = urllib2.urlopen(config.components_json_url, timeout=config.webservices_timeout)
		data = obj.read()
		obj.close()
		obj = urllib2.urlopen("%s.sign" % config.components_json_url, timeout=config.webservices_timeout)
		sign = obj.read()
		obj.close()
		
		assert utils.verify_signature(data, sign, config.pubkey_path)
		log.debug('components_json_url signature check passed')
		return json.loads(data, object_pairs_hook=OrderedDict)
	except:
		log.error('components_json_url signature check FAILED:')
		log.error('config.components_json_url = %s' % config.components_json_url)
		log.error(traceback.format_exc())
		return {}
	
@utils.decorators.retry(Exception, logger=log)
@utils.decorators.memoize(config.memoize_timeout)
def get_packages_data():
	"Function queries the iQuality website for packages json data"
	try:
		obj = urllib2.urlopen(config.packages_json_url, timeout=config.webservices_timeout)
		data = obj.read()
		obj.close()
		obj = urllib2.urlopen("%s.sign" % config.packages_json_url, timeout=config.webservices_timeout)
		sign = obj.read()
		obj.close()
		
		assert utils.verify_signature(data, sign, config.pubkey_path)
		log.debug('packages_json_url signature check passed')
		return json.loads(data, object_pairs_hook=OrderedDict)
	except:
		log.error('packages_json_url signature check FAILED:')
		log.error(traceback.format_exc())
	return {}