# ML Kit и Firebase находят свои компоненты по именам классов из манифеста
# и создают их рефлексией через пустой конструктор. R8 в full mode (AGP 9)
# вырезал эти конструкторы — BarcodeRegistrar не создавался, и в release
# BarcodeScanning.getClient() падал с NullPointerException: QR-сканер
# не запускался ни на одном Android-устройстве.
-keep class * implements com.google.firebase.components.ComponentRegistrar {
    <init>();
}
