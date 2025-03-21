# -*- coding: utf-8 -*-
###############################################################
# Máster de Ciencia de Datos - UOC                            #
# M2.851 - Tipología y ciclo de vida de los datos             #
# Práctica 1 - Web Scraping                                   #
# nutriscraper.py                                             #  
#                                                             #
# Autores:                                                    #
#   Azucena González (azucenagm)                              #
#   Jesús Márquez (jmarquez01)                                #
###############################################################

# Clase que realiza web scraping sobre la web de información nutricional bedca.net, que contiene la 
# Base de Datos Española de Composición de Alimentos

from bs4 import BeautifulSoup
import constants
import csv
import requests
import sys
import time
import urllib.robotparser
import json
import os

class NutriScraper:
    # Método constructor: crea el archivo de salida y genera las líneas de cabecera
    def __init__(self):
        # Se inicializa el objeto que mantendrá los resultados
        self.results = []
        
        # Se verifica si ya existe un archivo JSON con datos previos
        if os.path.exists(constants.JSON_OUTPUT_FILE) and os.path.getsize(constants.JSON_OUTPUT_FILE) > 0:
            try:
                with open(constants.JSON_OUTPUT_FILE, 'r', encoding='utf-8') as json_file:
                    self.results = json.load(json_file)
                print(f"Cargados {len(self.results)} registros existentes del archivo JSON")
            except json.JSONDecodeError:
                print("Error al cargar el archivo JSON existente. Se creará uno nuevo.")
                self.results = []
        
        # Para mantener compatibilidad, también se inicializa el archivo CSV
        self._write2csv(constants.CSV_OUTPUT_FILE, constants.CSV_HEADER, 'w')

    # Método que ejecuta el proceso de scraping: se conecta a la URL, descarga la información y gestiona su
    # procesamiento y volcado a fichero
    def execute(self):
        # Se comprueba si el fichero robots.txt permite el acceso del web scraper
        if not self._accessGranted():
            print("Acceso no permitido por el fichero robots.txt. Se aborta el programa")
            sys.exit(1)
            
        # Se recogen todos los identificadores de los alimentos existentes
        print("Solicitando los identificadores de los alimentos")
        foodList = self._getFoodIds()
      
        # Se extrae la información detallada de cada uno de los alimentos
        print("Iniciando la captura de los datos nutricionales de todos los alimentos")
        self._getFoodDetails(foodList)

    # Método que comprueba si el user agent del web scraper programado puede acceder a la página de peticiones
    # o no siguiendo las indicaciones del fichero robots.txt
    def _accessGranted(self):
        # Se crea un parseador de ficheros robots.txt
        rp = urllib.robotparser.RobotFileParser()
        
        # Se asigna la URL completa donde debe estar el fichero robots.txt y se lee su contenido
        rp.set_url(constants.ROBOTS_URL)
        rp.read()
        
        # Devuelve si está permitido el acceso para el user-agent suministrado a la URL de peticiones. En caso
        # de que no exista el fichero robots.txt, la función can_fetch devuelve True
        return rp.can_fetch(constants.USER_AGENT, constants.URL)

    # Método que realiza la petición suministrada por parámetro 
    def _getRequest(self, url, request, headers):      
        # Se intenta establecer la conexión: en caso de error, se interrumpirá la ejecución del programa
        try:
            r = requests.post(url, data=request, headers=headers)
                            
        except requests.exceptions.RequestException as exception:
            print("No se ha podido establecer la conexión [" + str(exception) + "]. Se aborta el programa")
            sys.exit(1)
        
        # Se devuelve la respuesta de la petición realizada
        return r

    # Método que realiza una petición para obtener los identificadores de todos los alimentos de la base de 
    # datos
    def _getFoodIds(self):
        # Petición para obtener el listado de alimentos
        r = self._getRequest(constants.URL, constants.IDS_REQUEST, constants.HEADERS)
        
        # Se pasa la información a un objeto soup utilizando BeautifulSoup con un parseador de XML
        soup = BeautifulSoup(r.text, "lxml-xml")
         
        # Se recogen los ids de los productos consultados y se guardan en una lista
        return [elemID.get_text() for elemID in soup.find_all('f_id')]

    # Obtención de la información nutricional de un listado de alimentos pasado como parámetro 
    def _getFoodDetails(self, foodList):
        # Lista de IDs ya procesados para evitar duplicados
        processed_ids = {item.get('f_id', None) for item in self.results}
        
        # Se solicita la información asociada a cada alimento realizando una petición por cada id encontrado
        for elemID in foodList:
            # Saltamos los elementos ya procesados en ejecuciones previas
            if elemID in processed_ids:
                print(f"El elemento {elemID} ya fue procesado anteriormente. Omitiendo.")
                continue
                
            try:
                # Diccionario donde se almacena la información de cada alimento
                elemInfoDict = {}
                
                # Petición para obtener el detalle nutricional de cada elemento
                detailsRequest = constants.DETAILS_REQUEST_INI + str(elemID) + constants.DETAILS_REQUEST_FIN
                
                # Se controla el tiempo de respuesta de la petición para añadir un retardo que evite saturar
                # el servidor
                initialTime = time.time()
                
                # Se realiza la petición
                r = self._getRequest(constants.URL, detailsRequest, constants.HEADERS)
                
                # Se calcula el tiempo de respuesta y se introduce una espera proporcional
                responseTime = time.time() - initialTime
                print("El tiempo de espera es: " + str(responseTime*constants.DELAY_FACTOR))
                time.sleep(responseTime * constants.DELAY_FACTOR)
                
                # Con r.content conseguimos que BS detecte correctamente la codificación de la respuesta
                # (UTF-8)
                soup = BeautifulSoup(r.content, "lxml-xml")
                
                # Se recoge la información básica de cada elemento y se almacena en el objeto diccionario
                for tag in constants.BASIC_LIST:
                    elemInfoDict[tag] = soup.find(tag).getText()
              
                # Se obtiene el nombre del nutriente, su valor y, para el caso en que el valor no esté
                # registrado, el campo tipo de valor, que proporciona información sobre la medición realizada
                components = soup.find_all('foodvalue')
                for comp in components:
                    # Se recoge el nombre, valor y tipo del nutriente
                    name = comp.find("c_ori_name").getText()
                    value = comp.find("best_location").getText()
                    valueType = comp.find("value_type").getText()
    
                    # Se comprueba si best_location está informado. En caso contrario, se le asignará a este 
                    # campo el valor de value_type
                    elemInfoDict[name] = (valueType if value == '' else value)
               
                # Se escribe la información a fichero
                print("Escritura a fichero del registro")
                self._write2csv(constants.CSV_OUTPUT_FILE, self._dictionary2csv(elemInfoDict), 'a')
                
                # Guardar en el objeto de resultados y actualizar el archivo JSON
                self.results.append(elemInfoDict)
                self._write2json()

            # Se captura la excepción de error de atributos
            except AttributeError as error:
                print("El elemento " + str(elemID) + " ha producido un error [" + str(error) + "]")
            
            # Se captura el resto de excepciones
            except Exception as exception:
                print("El elemento " + str(elemID) + " ha generado una excepción [" + str(exception) + "]")
        
    # Método que recupera los valores nutricionales de un alimento y genera una línea con la información
    # para su posterior inserción en el fichero de salida
    def _dictionary2csv(self, dictionary): 
        # Se recorren los campos necesarios para el CSV y se extrae (si existe) su información del diccionario
        # del elemento actual
        line = []       
        for elem in constants.CSV_HEADER:
            # Si el alimento no contiene el nutriente indicado en la cabecera, se informará con un valor que 
            # refleje que dicha información no está disponible (constants.EMPTY)
            line.append(dictionary.get(elem, constants.EMPTY))
        
        print(line)
        return(line)

    # Método que escribe una línea a fichero        
    def _write2csv(self, file, line, mode):
        # Se abre el fichero en modo "append" para añadir una línea con los detalles nutricionales de un
        # alimento
        try:
            with open(file, mode, newline='') as csvFile:
                writer = csv.writer(csvFile)
                writer.writerow(line)
        # Se captura el resto de excepciones
        except Exception as exception:
            print("No se ha podido escribir en fichero [" + str(exception) + "]. Se aborta el programa")
            sys.exit(1)

    # Método que escribe los resultados al archivo JSON
    def _write2json(self):
        try:
            with open(constants.JSON_OUTPUT_FILE, 'w', encoding='utf-8') as json_file:
                json.dump(self.results, json_file, ensure_ascii=False, indent=2)
        except Exception as exception:
            print(f"No se ha podido escribir en el archivo JSON [{str(exception)}]")
            # No abortamos el programa para permitir que se siga ejecutando
            # y guardar lo que se pueda en el archivo CSV
