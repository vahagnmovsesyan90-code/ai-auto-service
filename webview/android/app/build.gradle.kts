import groovy.json.JsonSlurper
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Push ծանուցումներ (զանգի հիշեցում). Firebase Console → Android app (am.aiauto.app) → google-services.json-ը դնել
// այս թղթապանակում (git-ում ՉԿԱ)։ Չկա՝ հավելվածը հավաքվում է առանց push-ի (հիշեցումը երևում է միայն բաց հավելվածում)
if (file("google-services.json").exists()) apply(plugin = "com.google.gms.google-services")

// Ընդհանուր կոնֆիգը՝ ../../app.json (նույնը կարդում է նաև iOS-ը)
@Suppress("UNCHECKED_CAST")
val cfg = JsonSlurper().parse(rootProject.file("../app.json")) as Map<String, Any>
@Suppress("UNCHECKED_CAST")
val androidCfg = cfg["android"] as Map<String, Any>
fun jsList(l: Any?) = (l as List<*>).joinToString(",") { "\"$it\"" }

android {
    namespace = "am.aiauto.app"
    compileSdk = 35

    defaultConfig {
        applicationId = androidCfg["applicationId"] as String
        minSdk = 26
        targetSdk = 35
        versionCode = (androidCfg["versionCode"] as Number).toInt()
        versionName = androidCfg["versionName"] as String

        buildConfigField("String", "APP_NAME", "\"${cfg["name"]}\"")
        buildConfigField("String", "UA_SUFFIX", "\"${cfg["userAgentSuffix"]}\"")
        manifestPlaceholders["appHost"] = (cfg["hosts"] as List<*>).first().toString()
    }

    // Release-ի ստորագրում. բանալին և գաղտնաբառերը git-ում ՉԿԱՆ (android/keystore.properties + *.jks, տես .gitignore)։
    // Ֆայլը չկա՝ release-ը մնում է unsigned, ինչպես առաջ. Android-ը unsigned APK չի տեղադրում
    val keystoreFile = rootProject.file("keystore.properties")
    val keystore = Properties().apply { if (keystoreFile.exists()) keystoreFile.inputStream().use { load(it) } }
    signingConfigs {
        if (keystoreFile.exists()) create("release") {
            storeFile = rootProject.file(keystore.getProperty("storeFile"))
            storePassword = keystore.getProperty("storePassword")
            keyAlias = keystore.getProperty("keyAlias")
            keyPassword = keystore.getProperty("keyPassword")
        }
    }

    buildTypes {
        debug {
            // Emulator-ից տեղական կայքը՝ 10.0.2.2:8090 (cleartext-ը թույլատրված է միայն debug manifest-ում)
            buildConfigField("String", "APP_URL", "\"${cfg["devUrl"]}\"")
            buildConfigField("String[]", "HOSTS", "{${jsList(cfg["hosts"])},${jsList(cfg["devHosts"])}}")
        }
        release {
            signingConfig = signingConfigs.findByName("release")
            buildConfigField("String", "APP_URL", "\"${cfg["url"]}\"")
            buildConfigField("String[]", "HOSTS", "{${jsList(cfg["hosts"])}}")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    sourceSets["main"].assets.srcDirs("../../shared")

    buildFeatures { buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("androidx.webkit:webkit:1.12.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("com.google.firebase:firebase-messaging:24.0.1")
}
