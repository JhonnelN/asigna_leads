from odoo import models, api, fields
from .feriados_latam import FeriadosLatam
import traceback
import datetime
import logging

logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.model
    def create(self, values):
        debug_log = True
        try:
            self.lead_name     = values.get('name')
            self.cliente       = values.get('contact_name')
            self.agente        = values.get('user_id')
            self.telf          = values.get('phone')
            self.mail          = values.get('email_from')
            self.localidad     = values.get('country_id')
            self.fecha_entrada = values.get('date_open')
            self.area_lead     = values.get('x_area_id')
            self.company       = values.get('company_id')
            self.fecha         = values.get('create_date')
            self.lead_id       = values.get('id')
            self.descripcion   = values.get('description')

            if self.no_es_sesion_clinica():
            # Main:

                #Activacion de Filtros por Paises ---------------------------------
                latinoamerica = [10, 14, 29, 46, 49, 50, 51, 63, 96, 156, 172, 173,
                                181, 185, 209, 234, 238, 299, 300, 305]
                europa        = [1, 57, 68, 75, 166]
                portugues     = [31, 183]

                #LATAM
                if (self.company == 1111): #or (self.localidad in latinoamerica):
                    lista_agentes = self.env['security.role'].browse(140).user_ids
                    self.agentes = self.genera_diccionario_agentes(lista_agentes)

                #BRASIL
                elif (self.company == 1118): #or (self.localidad in portugues):
                    lista_agentes = self.env['security.role'].browse(141).user_ids
                    self.agentes = self.genera_diccionario_agentes(lista_agentes)

                else:
                    res = super(CrmLead, self).create(values)
                    logger.info(
                         "Lead no se asigno automaticamente, la compañia {} no tiene asignacion automatica".format(self.company))
                    return res
                
                # ----------------------------------------------------------------
                # Info
                logger.info( "Compañia: {}".format( self.company ) )
                logger.info( "Localidad: {}".format( self.localidad ) )
                logger.info( "Lead Name: {}".format(self.lead_name) )
                logger.info( "E-mail: {}".format(self.mail) )
                logger.info( "Area Lead: {}".format(self.area_lead) )
                # Filtrado: Parte 1 ----------------------------------------------
                vacaciones_status  = self.filtro_vacaciones() # Funcional 21/06/2021
                if debug_log:
                    logger.info("Filtrado vacaciones: {}".format(len(self.diccionario_agentes.keys())))
                feriado_status     = self.filtro_feriado()    # Checar
                if debug_log:
                    logger.info("Filtrado feriado: {}".format(len(self.diccionario_agentes.keys())))
                horario_status     = self.filtro_horario()    # Funcional 02/07/2021 
                if debug_log:    
                    logger.info("Filtrado horario: {}".format(self.diccionario_agentes.keys()))
                attrs = {
                    'register_date'    : self.fecha,
                    'pais_lead'        : self.localidad,
                    'filtro_vacaciones': vacaciones_status,
                    'filtro_feriado'   : feriado_status,
                    'filtro_horario'   : horario_status
                }
                # Asignacion: Caso 1 (Cliente atendido anteriormente) ------------
                # anterior_status   = self.asigna_anterior_agente() 
                anterior_status = False
                if anterior_status:
                    agent = self.agente_previo
                    values.update({'user_id': agent})
                    attrs['agente_lead']                 = agent
                    attrs['filtro_atendido_previamente'] = anterior_status
                    # Debug 3
                    logger.info(
                     "Fue atendido anteriormente por: {}".format(agent))

                if anterior_status == False:
                    # Debug 4
                    logger.info(
                    "No fue atendido anteriormente")

                # -----------------------------------------------------------
                # Filtrado: Parte 2 -----------------------------------------
                    area_status             = self.filtro_area_agente()
                    logger.info("Filtrado Area agente: {}".format(self.diccionario_agentes.keys()))
                    preferencia_pais_status = self.filtro_preferencia_pais()
                    logger.info("Filtrado preferencia pais: {}".format(self.diccionario_agentes.keys()))
                    self.filtro_diario_max_leads() # funcional
                    logger.info("Filtrado filtrado max diarios: {}".format(self.diccionario_agentes.keys()))
                    max_lead_status         = self.filtro_num_max_leads() # Funcional
                    logger.info("Filtrado filtrado max leads al mismo tiempo: {}".format(self.diccionario_agentes))
                    if len(self.diccionario_agentes)==0:
                        res = super(CrmLead, self).create(values)
                        return res
                # -----------------------------------------------------------
                # Asignacion: Caso 2 (Cliente nuevo) ------------------------
                    agent = self.asigna_nuevo_agente()
                    values.update({'user_id': agent})
                    attrs['agente_lead']       = agent
                    attrs['filtro_area_curso'] = area_status
                    attrs['filtro_pais']       = preferencia_pais_status
                    attrs['filtro_max_lead']   = max_lead_status

                # Create: Registro de la asignacion.
                lead_log = self.env['lead.logs'].create(attrs)

                res = super(CrmLead, self).create(values)
                self.env.cr.execute(
                    """ UPDATE crm_lead SET user_id = %s WHERE id = %s""" % (
                        agent or 'NULL', res.id))
                lead_log.update({'lead_id': res.id})
                return res

            else:
                res = super(CrmLead, self).create(values)
                return res

        except Exception as e:
            logger.exception(e)
            # logger.info(e.__traceback__)
            res = super(CrmLead, self).create(values)
            return res

    def genera_diccionario_agentes(self, agentes):
        self.diccionario_agentes = {}
        lista_agentes_venta_asesor = []
        
        for agente in agentes:
            lista_agentes_venta_asesor.append(agente.id)

        for agente in lista_agentes_venta_asesor:
            # atributos_agente 
            # 0 cantidad leads pending
            # 1 tasa conv
            # 2 vacaciones inicio
            # 3 vacaciones fin
            # 4 horario
            # 5 area
            # 6 leads max
            # 7 pais
            # 8 leads max diarios
            atributos_agente = []
            cant_leads = 0
            leads_won = []
            leads_totales_agente = self.env['crm.lead'].search(
                [('user_id', '=', agente)])

            for leads in leads_totales_agente:
                # Calculo de leads pendientes sin atender del agente
                if (leads.won_status == 'pending') and (leads.type == 'lead'): 
                    cant_leads += 1
                # Calculo de tasa de conversion
                if (leads.won_status == 'won'):
                    leads_won.append(leads)
            # Atributo 0 cantidad leads pending
            atributos_agente.append(cant_leads)

            try:
                tasat_conv = len(leads_won) / len(leads_totales_agente)
            except:
                tasat_conv = 0
            # Atributo 1 tasa conv
            atributos_agente.append(tasat_conv)
            # Carga atributos del modelo
            atributos_modelo = self.env['atributos.agentes'].search(
                [('agente_name', '=', agente)])
            # Atributo 2 vacaciones inicio
            atributos_agente.append(atributos_modelo.vacaciones_inicio)
            # Atributo 3 vacaciones fin
            atributos_agente.append(atributos_modelo.vacaciones_fin)
            # Atributo 4 horario
            atributos_agente.append(atributos_modelo.horario_laboral)
            # Atributo 5 area curso
            atributos_agente.append(atributos_modelo.area_curso)
            # Atributo 6 leads maximos
            atributos_agente.append(atributos_modelo.max_leads)
            # Atributo 7 pais
            atributos_agente.append(atributos_modelo.pais) 
            # Atributo 8 leads max diarios
            atributos_agente.append(atributos_modelo.max_diarios) 
           

            self.diccionario_agentes[agente] = atributos_agente
        
        return self.diccionario_agentes
           
     
    def filtro_vacaciones(self):
        now = datetime.datetime.now()
        dia = int(now.strftime("%d"))
        mes = int(now.strftime("%m"))
        fecha_actual     = (mes, dia)    
        black_list       = []
        ejecucion        = False
       

        for agente in self.diccionario_agentes:
            vacaciones_inicio = self.diccionario_agentes[agente][2]
            vacaciones_fin    = self.diccionario_agentes[agente][3]

            if (vacaciones_inicio != False) and (
                vacaciones_fin    != False):

                inicio_vacaciones = (
                    int(vacaciones_inicio.strftime("%m")),
                    int(vacaciones_inicio.strftime("%d"))
                )

                fin_vacaciones = (
                    int(vacaciones_fin.strftime("%m")),
                    int(vacaciones_fin.strftime("%d"))
                )

                if (fecha_actual[1] >= inicio_vacaciones[1]) and (
                        fecha_actual[0] == inicio_vacaciones[0]) or (
                        fecha_actual[0] > inicio_vacaciones[0]) and (
                        fecha_actual[0] <= fin_vacaciones[0]):
                    black_list.append(agente)
                    ejecucion = True

        for agente in black_list:
            del self.diccionario_agentes[agente]
        if ejecucion == True:
            return True
        else:
            return False

    def filtro_feriado(self):

        feriados   = FeriadosLatam()
        now        = datetime.datetime.now()
        dia        = int(now.strftime("%d"))
        mes        = int(now.strftime("%m"))
        fecha      = (mes, dia)
        paises     = []
        black_list = []
        ejecucion  = False

        feriados_mexico    = feriados.mexico()
        feriados_colombia  = feriados.colombia()
        feriados_salvador  = feriados.salvador()
        feriados_nicaragua = feriados.nicaragua()
        feriados_venezuela = feriados.venezuela()
        feriados_honduras  = feriados.honduras()

        for i in feriados_mexico:
            if fecha == i:
                paises.append(156)
                ejecucion = True
        for i in feriados_colombia:
            if fecha == i:
                paises.append(49)
                ejecucion = True
        for i in feriados_salvador:
            if fecha == i:
                paises.append(209)
                ejecucion = True
        for i in feriados_nicaragua:
            if fecha == i:
                paises.append(164)
                ejecucion = True
        for i in feriados_venezuela:
            if fecha == i:
                paises.append(238)
                ejecucion = True
        for i in feriados_honduras:
            if fecha == i:
                paises.append(299)
                ejecucion = True

        if ejecucion:
            for agente in self.diccionario_agentes:
                pais_agente = self.diccionario_agentes[agente][7]

                if pais_agente in paises:
                    black_list.append(agente)
            if len(black_list)>0:        
                for agente in black_list:
                    del self.diccionario_agentes[agente]
                return True
            else:
                return False
        else:
            return False

    def filtro_horario(self):
        dia     = int(datetime.datetime.now().weekday())
        hora       = int(datetime.datetime.now().strftime('%H'))
        black_list = []
        horario_6  = [156,299,164,209]
        horario_5  = [156,49]
        agente_eliminado = False

        logger.info(" Filtro horario dia: {} hora: {}".format(dia, hora))

        #Creacion de la lista de agentes
        for agente in self.diccionario_agentes:
            ejecucion      = False
            horario_agente = self.diccionario_agentes[agente][4]
            pais_agente    = self.diccionario_agentes[agente][7]
            if horario_agente == "7":
                if (hora - 4 in range(7, 13)) and (dia in range(5)) and (pais_agente == 238):
                    ejecucion = True

                elif (hora - 5 in range(7, 13)) and (dia in range(6)) and (pais_agente in horario_5):
                    ejecucion = True
                    
                
                elif (hora - 6 in range(7, 13)) and (dia in range(6)) and (pais_agente in horario_6):
                    ejecucion = True

            elif horario_agente == "9":
                if (hora - 4 in range(9, 15)) and (dia in range(5)) and (pais_agente == 238):
                    ejecucion = True

                elif (hora - 5 in range(9, 15)) and (dia in range(6)) and (pais_agente in horario_5):
                    ejecucion = True 
                
                elif (hora - 6 in range(9, 15)) and (dia in range(6)) and (pais_agente in horario_6):
                    ejecucion = True

            elif horario_agente == "Tiempo completo":
                ejecucion = True
            
            if ejecucion == False:
                black_list.append(agente)

        if len(black_list)>0 and len(black_list) != len(self.diccionario_agentes):        
                for agente in black_list:
                    del self.diccionario_agentes[agente] 
                    agente_eliminado = True   

        if agente_eliminado:
            return True
        else:
            return False

    def viejo_lead(self):

        telf      = self.telf
        mail      = self.mail
        cliente   = self.cliente 
        lead_name = self.lead_name

        if (lead_name != False):
            leads_semejantes = self.env['crm.lead'].search(
                [('name', '=', lead_name)])
            if len(leads_semejantes)>0:
                nombre_agente = leads_semejantes[0].user_id.id
                # Debug 5
                logger.info(
                "Nombre del lead coincide: {} status del lead anterior: {}".format(nombre_agente,leads_semejantes[0].won_status))
                if leads_semejantes[0].won_status == 'won':
                    return nombre_agente
            
        elif (mail != False):
            leads_semejantes = self.env['crm.lead'].search(
                [('email_from', '=', mail)])
            if len(leads_semejantes)>0:
                nombre_agente = leads_semejantes[0].user_id.id
                # Debug 5
                logger.info(
                "Direccion de mail coincide: {} status del lead anterior: {}".format(nombre_agente,leads_semejantes[0].won_status))
                if leads_semejantes[0].won_status == 'won':
                    return nombre_agente

        elif (telf != False):
            leads_semejantes = self.env['crm.lead'].search(
                [('phone', '=', telf)])
            if len(leads_semejantes)>0:
                nombre_agente = leads_semejantes[0].user_id.id
                # Debug 5
                logger.info(
                "Telefono coincide: {} status del lead anterior: {}".format(nombre_agente,leads_semejantes[0].won_status))
                if leads_semejantes[0].won_status == 'won':
                    return nombre_agente
            

        elif (cliente != False):
            leads_semejantes = self.env['crm.lead'].search(
                [('contact_name', '=', cliente)])
            if len(leads_semejantes)>0:
                nombre_agente = leads_semejantes[0].user_id.id
                # Debug 5
                logger.info(
                "Nombre de cliente coincide: {} status del lead anterior: {}".format(nombre_agente,leads_semejantes[0].won_status))
                if leads_semejantes[0].won_status == 'won':
                    return nombre_agente

        else:
            return False

    def asigna_anterior_agente(self):
        if self.viejo_lead() != False:
            self.agente_previo = self.viejo_lead()

        for agente in self.diccionario_agentes:
            if agente == self.agente_previo:
                return True
        return False
    def area_del_lead(self):
        lead_name_short = self.lead_name[0:2]
        neurociencias = ["NP","TH","MN","NR","ND","NE","FN","EN","RC","NI"]
        clinica       = ["MP","PC","MI","PF","ML","MS","CP","AA","AC","BE",
                         "CT","EM","AD","CA","TF","IE","LD","SE","PO"]
        educacion     = ["AT","AU","ES","ED","PV","AP","DA","BU","PM","IC",
                         "MA","TB","AE","TT","MM","AR"]
        logopedia     = ["LP","LC","FM"]
        empresas      = ["AM","DC"]
        if lead_name_short in clinica:
            return 1
        elif lead_name_short in educacion:
            return 2
        elif lead_name_short in logopedia:
            return 3
        elif lead_name_short in neurociencias:
            return 4
        elif lead_name_short in empresas:
            return 5


    def filtro_area_agente(self):
        aux_dic   = {}
        area_lead = self.area_del_lead()
        
        for agente in self.diccionario_agentes:
            area_agent = list(self.diccionario_agentes[agente][5])
            if area_lead in area_agent:
                aux_dic[agente] = self.diccionario_agentes[agente]

        if len(aux_dic)>0:
            self.diccionario_agentes = aux_dic
            return True

        else:
            return False

    def filtro_preferencia_pais(self):
        aux_dic= {}
        pais_lead = self.localidad

        for agente in self.diccionario_agentes:
            pais_agente = self.diccionario_agentes[agente][7]
            if pais_agente == pais_lead:
            
                aux_dic[agente] = self.diccionario_agentes[agente]

        if len(aux_dic)>0:
            self.diccionario_agentes = aux_dic
            return True
        else:
            return False
    def leads_asignados_hoy(self, agente):
        contador = 0
        lead_logs = self.env['lead.logs'].search(
                [('agente_lead', '=', agente)])
        for leads in lead_logs:
            if leads.create_date.date() == datetime.datetime.now().date():
                contador = contador + 1
      
        
        return contador        
    def filtro_diario_max_leads(self):
        ejecucion = False
        black_list = []
        for agente in self.diccionario_agentes:
            max_leads_diarios_permitidos = self.diccionario_agentes[agente][8]
            leads_asignados_hoy          = self.leads_asignados_hoy(agente)
            if leads_asignados_hoy >= max_leads_diarios_permitidos:
                ejecucion = True
                black_list.append(agente)

        if ejecucion:        
            for agente in black_list:
                del self.diccionario_agentes[agente] 

        if len(self.diccionario_agentes)==0:
            logger.info(
                    "Los agentes estan a full capacidad")
            return True

        if ejecucion:
            return True
        else:
            return False

    def filtro_num_max_leads(self):
        ejecucion = False
        black_list = []
        for agente in self.diccionario_agentes:
            max_leads_permitidos = self.diccionario_agentes[agente][6]
            leads_pending        = self.diccionario_agentes[agente][0]
            if max_leads_permitidos <= leads_pending:
                ejecucion = True
                black_list.append(agente)

        if ejecucion:        
                for agente in black_list:
                    del self.diccionario_agentes[agente] 

        if len(self.diccionario_agentes)==0:
            logger.info(
                    "Los agentes estan a full capacidad")
            return True

        if ejecucion:
            return True
        else:
            return False

    def asigna_nuevo_agente(self):
        # Agente con menos leads pending
        agente_final = min(self.diccionario_agentes, key = self.diccionario_agentes.get)
        logger.info(
                "Agente Final: {}".format(agente_final))
        return agente_final

    def no_es_sesion_clinica(self):
        sesion_clinica = [
           "Noaplicallamadas",
            "No es alumno", 
            "Sesión Clínica",
            "No es alumno Sesión Clínica",
            "No es alumno\nSesión Clínica",
            "Sí es alumno Sesión Clínica",
            "Sí es alumno\nSesión Clínica", 
	        "Sí es alumno" 
	        ]
        if self.descripcion in sesion_clinica:
            return False
        else:
            return True