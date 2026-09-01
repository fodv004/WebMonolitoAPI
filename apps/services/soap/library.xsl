<?xml version="1.0" encoding="UTF-8"?>
<!--
  library.xsl
  Pure XSLT 1.0 transform: re-hosts library02.xml's own element names inside
  a real HTML document (adding a real <img> for the cover) so that the
  already-built estilo.css keeps styling every tag exactly as before.
  No JavaScript is used anywhere in this pipeline.
-->
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:lib="urn:libreria:soap:library"
    exclude-result-prefixes="lib">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/lib:library">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <title><xsl:value-of select="@name"/></title>
        <link rel="stylesheet" type="text/css" href="estilo.css"/>
      </head>
      <body>
        <library name="{@name}">
          <xsl:apply-templates select="lib:book"/>
        </library>
      </body>
    </html>
  </xsl:template>

  <xsl:template match="lib:book">
    <xsl:variable name="cover" select="lib:images/lib:image[@main='true'][1]"/>
    <book>
      <xsl:if test="$cover">
        <img class="cover" src="{$cover}" alt="{lib:title}"/>
      </xsl:if>

      <isbn><xsl:value-of select="lib:isbn"/></isbn>
      <title><xsl:value-of select="lib:title"/></title>

      <authors>
        <xsl:for-each select="lib:authors/lib:author">
          <author>
            <name><xsl:value-of select="lib:name"/></name>
            <nationality><xsl:value-of select="lib:nationality"/></nationality>
          </author>
        </xsl:for-each>
      </authors>

      <genres>
        <xsl:for-each select="lib:genres/lib:genre">
          <genre><xsl:value-of select="."/></genre>
        </xsl:for-each>
      </genres>

      <publicationYear><xsl:value-of select="lib:publicationYear"/></publicationYear>
      <price><xsl:value-of select="lib:price"/></price>
      <stock><xsl:value-of select="lib:stock"/></stock>
      <format><xsl:value-of select="lib:format"/></format>

      <images>
        <xsl:for-each select="lib:images/lib:image">
          <image main="{@main}" order="{@order}"><xsl:value-of select="."/></image>
        </xsl:for-each>
      </images>

      <xsl:choose>
        <xsl:when test="lib:concepts/lib:concept">
          <concepts>
            <xsl:for-each select="lib:concepts/lib:concept">
              <concept>
                <name><xsl:value-of select="lib:name"/></name>
                <definition><xsl:value-of select="lib:definition"/></definition>
              </concept>
            </xsl:for-each>
          </concepts>
        </xsl:when>
        <xsl:otherwise>
          <concepts/>
        </xsl:otherwise>
      </xsl:choose>
    </book>
  </xsl:template>

</xsl:stylesheet>
