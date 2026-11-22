FROM quay.io/keycloak/keycloak:26.8.2-3

USER 0
ADD --checksum=sha256:b530942257fb935f8b2cfaa5f8eb5bd59c555fd8e8d01b8ce98912e077ea606c \
    https://repo1.maven.org/maven2/com/google/guava/guava/33.7.2-jre/guava-33.7.2-jre.jar \
    /opt/keycloak/lib/lib/main/com.google.guava.guava-33.6.0-jre.jar
RUN chown 1000:0 /opt/keycloak/lib/lib/main/com.google.guava.guava-33.6.0-jre.jar \
    && chmod 0444 /opt/keycloak/lib/lib/main/com.google.guava.guava-33.6.0-jre.jar
USER 1000
