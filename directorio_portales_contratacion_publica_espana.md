# Portales de contratación pública en España: directorio e interfaces de consulta

**Fecha de recopilación:** 18 de noviembre de 2026

Este documento reúne los portales de contratación pública españoles
identificados, sus direcciones web y los mecanismos de integración
disponibles para consultar licitaciones: API REST, JSON, XML/ATOM, RSS y
descargas de datos.

> **Nota importante:** no todos los portales ofrecen una API REST.
> Algunos publican datos mediante feeds ATOM/RSS, ficheros descargables
> o plataformas interoperables con la Plataforma de Contratación del
> Sector Público (PLACSP). Antes de utilizar una fuente en producción
> conviene comprobar su disponibilidad, frecuencia de actualización,
> cobertura e histórico.

------------------------------------------------------------------------

## 1. Fuentes nacionales

### 1.1. Plataforma de Contratación del Sector Público (PLACSP)

-   **Nombre:** Plataforma de Contratación del Sector Público.
-   **Organismo:** Ministerio de Hacienda -- Administración General del
    Estado.
-   **Portal:** <https://contrataciondelestado.es/>
-   **Tipo de integración:** sindicación ATOM/XML, datos CODICE y
    descargas históricas.
-   **Autenticación:** los feeds públicos indicados no requieren API Key
    ni usuario.
-   **Uso:** fuente principal para consultar perfiles de contratante
    alojados en PLACSP y licitaciones procedentes de plataformas
    autonómicas agregadas.

La PLACSP incluye perfiles de contratante de la Administración General
del Estado y de entidades autonómicas y locales adheridas. También
recibe información de otras plataformas mediante mecanismos de
agregación.

#### Feeds de sindicación

  -------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  Código                  Contenido               Endpoint
  ----------------------- ----------------------- -------------------------------------------------------------------------------------------------------------------------
  643                     Licitaciones de         <https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom>
                          perfiles alojados en    
                          PLACSP, excluyendo      
                          contratos menores       

  1044                    Licitaciones de         <https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom>
                          plataformas externas    
                          agregadas, sin          
                          contratos menores       

  1143                    Contratos menores de    <https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/contratosMenoresPerfilesContratantes.atom>
                          perfiles alojados en    
                          PLACSP                  
  -------------------------------------------------------------------------------------------------------------------------------------------------------------------------

**Características técnicas:**

-   Protocolo: HTTP/HTTPS.
-   Formato: XML basado en ATOM y CODICE.
-   Autenticación: no se requiere API Key ni usuario para los feeds
    públicos.
-   Actualización: los feeds de sindicación se actualizan de forma
    continua/diaria, aunque pueden producirse retrasos.
-   Contenido: anuncios, datos de expedientes y actualizaciones de
    licitaciones.
-   Paginación: los feeds contienen como máximo 500 entradas y utilizan
    un enlace `next` para recuperar las siguientes.
-   Tratamiento: un mismo expediente puede aparecer varias veces cuando
    se modifica; hay que procesar las actualizaciones y evitar insertar
    duplicados.

**Documentación técnica:**

-   Especificación de sindicación ATOM/CODICE:
    <https://www.hacienda.gob.es/DGPatrimonio/Plataforma_Contratacion/especificacion-sindicacion-1-3.pdf>
-   Datos abiertos de licitaciones PLACSP:
    <https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/paginas/licitaciones_plataforma_contratacion.aspx>

**Históricos y descargas masivas:**

-   Histórico de licitaciones de perfiles alojados:
    <https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/LicitacionesContratante.aspx>
-   Histórico de licitaciones de plataformas agregadas:
    <https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/LicitacionesAgregacion.aspx>
-   Histórico de contratos menores:
    <https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/Paginas/ContratosMenores.aspx>

**Listado de órganos de contratación:**

-   Fichero Excel:
    <https://contrataciondelsectorpublico.gob.es/datosabiertos/OrganosContratacion.xlsx>

Este fichero permite construir un catálogo de entidades y órganos de
contratación y relacionarlo con las licitaciones recibidas.

**Advertencia operativa:** en noviembre de 2026 se habían señalado
retrasos de actualización en la sindicación estatal. En particular, se
indicó que el feed 643 seguía mostrando publicaciones del día 15 en una
consulta del 17 de noviembre. Conviene implementar controles de
antigüedad de los datos, alertas y recuperación de información.

### 1.2. TED -- Tenders Electronic Daily

-   **Nombre:** Tenders Electronic Daily (TED).
-   **Organismo:** Oficina de Publicaciones de la Unión Europea.
-   **Portal:** <https://ted.europa.eu/>
-   **Tipo de integración:** REST API v3.
-   **Autenticación:** la Search API pública no requiere autenticación.
-   **Uso:** anuncios de contratación publicados a escala europea,
    incluidas licitaciones españolas sujetas a publicidad europea.

**API:**

-   Endpoint de búsqueda:
    `POST https://api.ted.europa.eu/v3/notices/search`
-   Formato de consulta: JSON.
-   Resultados/documentos: XML descargable, según el servicio.
-   Documentación: <https://docs.ted.europa.eu/api/latest/search.html>
-   Interfaz de documentación/Swagger:
    <https://api.ted.europa.eu/api/documentation/index.html>

TED complementa la PLACSP, pero no la sustituye. Es necesario deduplicar
los anuncios que aparecen en ambas fuentes.

------------------------------------------------------------------------

## 2. Portales de contratación de las comunidades autónomas

La siguiente tabla recoge las 17 comunidades autónomas, con el portal
identificado y el mecanismo de consulta o integración indicado en la
recopilación.

  ----------------------------------------------------------------------------------------------------------------------------------------------
  Comunidad autónoma      Portal oficial                                                                                 Sistema de consulta /
                                                                                                                         integración
  ----------------------- ---------------------------------------------------------------------------------------------- -----------------------
  Andalucía               <https://www.juntadeandalucia.es/temas/contratacion-publica/perfiles-licitaciones.html>        Plataforma propia
                                                                                                                         interconectada con
                                                                                                                         PLACSP.

  Aragón                  <https://contratacionpublica.aragon.es/licitaciones/visor/licitaciones/listado>                Gestor de Licitaciones
                                                                                                                         de Aragón (GLIC). Visor
                                                                                                                         propio; no se localizó
                                                                                                                         una API pública
                                                                                                                         documentada.

  Asturias                <https://perfil.asturias.es/>                                                                  PLACSP.

  Baleares                <https://plataformadecontractacio.caib.es/>                                                    Portal con información
                                                                                                                         histórica. Desde el
                                                                                                                         24/07/2017 las
                                                                                                                         entidades autonómicas
                                                                                                                         publican en PLACSP.

  Canarias                <https://www.gobiernodecanarias.org/hacienda/contratacion/>                                    Las nuevas licitaciones
                                                                                                                         se publican en PLACSP;
                                                                                                                         el portal propio
                                                                                                                         conserva información
                                                                                                                         histórica.

  Cantabria               <https://www.cantabria.es/perfil-contratante>                                                  PLACSP.

  Castilla-La Mancha      <https://contratacion.castillalamancha.es/perfil-de-contratante-del-sector-publico-regional>   Perfiles alojados en
                                                                                                                         PLACSP.

  Castilla y León         <https://contratacion.jcyl.es/web/es/contratacion-administrativa.html>                         PLACSP.

  Cataluña                <https://contractaciopublica.cat/ca/>                                                          Plataforma propia y
                                                                                                                         API/datos abiertos.

  Comunidad Valenciana    <https://contrataciondelestado.es/>                                                            Los perfiles de los
                                                                                                                         órganos de la
                                                                                                                         Generalitat consultados
                                                                                                                         se encuentran en
                                                                                                                         PLACSP.

  Extremadura             <https://contrataciondelestado.es/>                                                            Perfiles de
                                                                                                                         contratación en PLACSP.

  Galicia                 <https://www.contratosdegalicia.gal/portada.jsp?lang=es>                                       Plataforma propia
                                                                                                                         interconectada con
                                                                                                                         PLACSP y fuentes RSS.

  Comunidad de Madrid     <https://contratos-publicos.comunidad.madrid/>                                                 Plataforma propia y
                                                                                                                         feed ATOM.

  Región de Murcia        <https://transparencia.carm.es/plataforma-de-contratacion-carm>                                Plataforma propia
                                                                                                                         interconectada con
                                                                                                                         PLACSP.

  Navarra                 <https://portalcontratacion.navarra.es/es/home>                                                Plataforma propia y
                                                                                                                         datos abiertos
                                                                                                                         JSON/CSV/XML.

  País Vasco              <https://www.contratacion.euskadi.eus/>                                                        Plataforma propia y API
                                                                                                                         REST.

  La Rioja                <https://www.larioja.org/contratacion-publica/es/perfil-contratante>                           Plataforma propia y
                                                                                                                         datos abiertos
                                                                                                                         CSV/JSON/XML.
  ----------------------------------------------------------------------------------------------------------------------------------------------

### 2.1. Integraciones autonómicas identificadas

#### País Vasco -- KontratazioA

-   **Portal:** <https://www.contratacion.euskadi.eus/>
-   **Documentación API:**
    <https://opendata.euskadi.eus/webopd00-apicontract/es/?api=procurements>
-   **Tipo:** API REST oficial.

Servicios identificados:

  Servicio                        Información
  ------------------------------- -------------------------
  CN -- Contracting Notices       Anuncios de licitación
  C -- Contracts                  Contratos registrados
  CA -- Contracting Authorities   Órganos de contratación
  CO -- Companies                 Empresas licitadoras

Permite acceder a publicaciones e información del sector público vasco,
incluidas administraciones forales y locales. La plataforma vasca está
interconectada con PLACSP.

#### Cataluña -- Plataforma de Serveis de Contractació Pública / datos abiertos

-   **Portal:** <https://contractaciopublica.cat/ca/>
-   **Dataset:**
    <https://analisi.transparenciacatalunya.cat/Economia/Contractaci-p-blica-a-Catalunya-publicacions-a-la-/ybgg-dgi6>
-   **Tipo:** API JSON / Socrata y descargas CSV/XML.

**Endpoint JSON:**

``` text
https://analisi.transparenciacatalunya.cat/api/v3/views/ybgg-dgi6/query.json?accessType=DOWNLOAD
```

El conjunto de datos recoge publicaciones de órganos de contratación
catalanes, incluyendo anuncios de licitación, evaluación, adjudicación y
formalización. Se indicó una actualización diaria y consulta pública sin
suscripción.

#### Comunidad de Madrid -- Feed ATOM

-   **Portal:** <https://contratos-publicos.comunidad.madrid/>
-   **Datos abiertos:**
    <https://contratos-publicos.comunidad.madrid/perfil-contratante/datos-abiertos>
-   **Tipo:** ATOM/XML oficial, con especificaciones CODICE.

**Endpoint:**

``` text
https://contratos-publicos.comunidad.madrid/feed/licitaciones2
```

Características indicadas:

-   XML basado en ATOM.
-   Especificaciones CODICE.
-   URL permanente.
-   Incluye novedades y actualizaciones de licitaciones anteriores.
-   Sin registro ni API Key.

Este feed es el mecanismo utilizado para interconectar la plataforma
madrileña con PLACSP.

#### Navarra -- Open Data

-   **Portal:** <https://portalcontratacion.navarra.es/es/home>
-   **Dataset:**
    <https://datosabiertos.navarra.es/es/dataset/anuncios-licitaciones>
-   **Tipo:** JSON / CSV oficial.

**Endpoint JSON:**

``` text
https://datosabiertos.navarra.es/datastore/dump/dda1af7c-0dcd-4992-9852-ded6b1e7625d?format=json&bom=True
```

Información disponible indicada:

-   Órgano convocante.
-   Tipo de contrato.
-   Procedimiento.
-   Presupuesto.
-   Valor estimado.
-   CPV.
-   Fecha de publicación.
-   Estado.
-   Plazo.

Se indicó actualización diaria e inclusión de anuncios del año en curso.

#### Galicia -- Contratos Públicos de Galicia / RSS

-   **Portal:** <https://www.contratosdegalicia.gal/portada.jsp?lang=es>
-   **Tipo:** RSS oficial.

Ejemplo de feed:

``` text
https://abertos.xunta.gal/catalogo/administracion-publica/-/dataset/0252/actualidade-plataforma-contratos-publicos/001/descarga-directa-ficheiro.rss
```

La plataforma dispone de diferentes fuentes RSS en el catálogo de datos
abiertos de la Xunta. Se identificaron feeds para concursos publicados
durante los últimos 15 días y para concursos cuyo plazo de presentación
está próximo a finalizar.

**Limitación:** los RSS son útiles para alertas, pero no constituyen por
sí solos una API completa del histórico de licitaciones. La plataforma
gallega también está interconectada con PLACSP.

#### La Rioja -- Open Data

-   **Portal:** <https://www.larioja.org/contratacion-publica/es>
-   **Tipo:** CSV / JSON / XLS / XML.

**Endpoint JSON identificado:**

``` text
https://ias1.larioja.org/opendata/download?r=Y2Q9MTc5fGNmPTA0
```

**Advertencia:** la ficha del catálogo consultada indicaba que la última
actualización de sus metadatos era de febrero de 2018. No se recomienda
utilizarlo como fuente de nuevas licitaciones sin comprobar primero que
el contenido sigue actualizándose.

------------------------------------------------------------------------

## 3. Ciudades autónomas

  ----------------------------------------------------------------------------------------------------------------------------------------
  Ciudad                  Portal                                                                                   Publicación actual
                                                                                                                   indicada
  ----------------------- ---------------------------------------------------------------------------------------- -----------------------
  Ceuta                   <https://www.ceuta.es/ceuta/economica/contratos>                                         PLACSP para las
                                                                                                                   contrataciones actuales
                                                                                                                   desde enero de 2025.

  Melilla                 <https://melilla.es/melillaportal/contratante/pc_principal1.jsp?codResi=1&language=es>   PLACSP desde el 9 de
                                                                                                                   marzo de 2018.
  ----------------------------------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 4. Ejemplos de conexión a las fuentes

### 4.1. Descarga de los feeds principales de PLACSP desde Linux

Los feeds públicos no requieren API Key.

``` bash
# Licitaciones de perfiles alojados en PLACSP
curl -L \
'https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom' \
-o licitaciones_placsp.atom

# Licitaciones de plataformas agregadas
curl -L \
'https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom' \
-o licitaciones_agregadas.atom

# Contratos menores
curl -L \
'https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/contratosMenoresPerfilesContratantes.atom' \
-o contratos_menores.atom
```

Después hay que procesar el XML/ATOM y los datos CODICE, identificar
cada expediente, seguir la paginación mediante el enlace `next` y
gestionar las modificaciones.

### 4.2. Consideraciones para TED

La búsqueda de anuncios se realiza mediante:

``` text
POST https://api.ted.europa.eu/v3/notices/search
```

La API utiliza una consulta JSON. La documentación oficial contiene la
estructura de búsqueda, los campos y los mecanismos para recuperar los
resultados.

------------------------------------------------------------------------

## 5. Arquitectura recomendada para centralizar las licitaciones

No es necesario desarrollar desde el principio 17 integraciones
independientes. Se recomienda una arquitectura de conectores por
prioridad.

### Nivel 1 -- Fuentes nacionales imprescindibles

1.  PLACSP 643: licitaciones de perfiles alojados.
2.  PLACSP 1044: licitaciones de plataformas autonómicas agregadas.
3.  PLACSP 1143: contratos menores.
4.  TED: publicaciones europeas.

### Nivel 2 -- Conectores autonómicos

Añadir conectores específicos para mejorar cobertura, detalle y
resiliencia:

-   País Vasco: API REST.
-   Cataluña: API JSON.
-   Comunidad de Madrid: ATOM.
-   Navarra: JSON.
-   Galicia: RSS.
-   La Rioja: solo después de comprobar la vigencia del conjunto de
    datos.

### Nivel 3 -- Resto de portales y organismos

Incorporar consultas específicas para organismos que no estén
correctamente representados en los feeds nacionales, así como:

-   Diputaciones.
-   Ayuntamientos.
-   Universidades.
-   Empresas públicas.
-   Otros entes del sector público.

### Recomendaciones técnicas

-   Mantener la trazabilidad de la fuente original de cada publicación.
-   Disponer de un identificador único y reglas de deduplicación por
    expediente y plataforma.
-   Conservar el histórico de modificaciones de cada licitación.
-   Procesar las actualizaciones, no limitarse a insertar registros
    nuevos.
-   Seguir la paginación de los feeds ATOM.
-   Controlar la fecha de última actualización de cada fuente.
-   Implementar alertas ante retrasos o caídas de los feeds.
-   Disponer de procesos de recuperación y carga histórica.
-   Contrastar periódicamente la cobertura de PLACSP con las plataformas
    autonómicas.
-   Evitar asumir que una licitación publicada en TED y en PLACSP
    representa dos expedientes distintos.

------------------------------------------------------------------------

## 6. Resumen ejecutivo de las fuentes con integración identificada

  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  Fuente            Mecanismo         Endpoint / documentación                                                                                                                                     Prioridad
  ----------------- ----------------- ------------------------------------------------------------------------------------------------------------------------------------------------------------ -----------------
  PLACSP 643        ATOM/XML          [Feed 643](https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom)                            Imprescindible

  PLACSP 1044       ATOM/XML          [Feed 1044](https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom)                                    Imprescindible

  PLACSP 1143       ATOM/XML          [Feed 1143](https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/contratosMenoresPerfilesContratantes.atom)                              Imprescindible

  TED               REST API v3       [Documentación](https://docs.ted.europa.eu/api/latest/search.html)                                                                                           Imprescindible

  País Vasco        REST              [API KontratazioA](https://opendata.euskadi.eus/webopd00-apicontract/es/?api=procurements)                                                                   Alta

  Cataluña          JSON / Socrata    [Dataset](https://analisi.transparenciacatalunya.cat/Economia/Contractaci-p-blica-a-Catalunya-publicacions-a-la-/ybgg-dgi6)                                  Alta

  Madrid            ATOM/XML          [Feed](https://contratos-publicos.comunidad.madrid/feed/licitaciones2)                                                                                       Alta

  Navarra           JSON              [Dataset](https://datosabiertos.navarra.es/es/dataset/anuncios-licitaciones)                                                                                 Alta

  Galicia           RSS               [Feed                                                                                                                                                        Media
                                      RSS](https://abertos.xunta.gal/catalogo/administracion-publica/-/dataset/0252/actualidade-plataforma-contratos-publicos/001/descarga-directa-ficheiro.rss)   

  La Rioja          JSON / CSV / XML  [Endpoint JSON](https://ias1.larioja.org/opendata/download?r=Y2Q9MTc5fGNmPTA0)                                                                               Verificar
                                                                                                                                                                                                   vigencia
  ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 7. Fuentes de referencia y documentación

-   [Plataforma de Contratación del Sector
    Público](https://contrataciondelestado.es/)
-   [Datos abiertos de contratación -- Ministerio de
    Hacienda](https://www.hacienda.gob.es/es-ES/GobiernoAbierto/Datos%20Abiertos/paginas/licitaciones_plataforma_contratacion.aspx)
-   [Especificación técnica de sindicación
    ATOM/CODICE](https://www.hacienda.gob.es/DGPatrimonio/Plataforma_Contratacion/especificacion-sindicacion-1-3.pdf)
-   [TED -- Tenders Electronic Daily](https://ted.europa.eu/)
-   [TED API Developer
    Docs](https://docs.ted.europa.eu/api/latest/search.html)
-   [Open Data Euskadi -- API de
    contratación](https://opendata.euskadi.eus/webopd00-apicontract/es/?api=procurements)
-   [Datos abiertos de Cataluña -- contratación
    pública](https://analisi.transparenciacatalunya.cat/Economia/Contractaci-p-blica-a-Catalunya-publicacions-a-la-/ybgg-dgi6)
-   [Datos abiertos de la Comunidad de
    Madrid](https://contratos-publicos.comunidad.madrid/perfil-contratante/datos-abiertos)
-   [Datos abiertos de Navarra -- anuncios de
    licitación](https://datosabiertos.navarra.es/es/dataset/anuncios-licitaciones)
-   [Datos abiertos de Galicia](https://abertos.xunta.gal/)

------------------------------------------------------------------------

## 8. Conclusión

Para una solución que centralice las licitaciones públicas españolas, el
punto de partida recomendado es **PLACSP 643 + 1044 + 1143 y TED**.
Después conviene incorporar las fuentes específicas de Euskadi,
Cataluña, Madrid y Navarra, y utilizar Galicia como fuente adicional de
alertas.

La cobertura no debe darse por garantizada únicamente por consumir el
feed estatal. Es importante contrastarla periódicamente con las
plataformas autonómicas, conservar la fuente original, deduplicar los
anuncios y mantener el histórico de cambios de cada expediente.

> **Nota de vigencia:** las direcciones, servicios, formatos y
> condiciones de actualización se han recopilado con referencia al 18 de
> noviembre de 2026. Antes de desplegar conectores en producción,
> comprueba la documentación y disponibilidad de cada servicio,
> especialmente los conjuntos de datos con advertencias de antigüedad.
