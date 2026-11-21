# Plan działania projektu: Detekcja fake newsów i grupowanie reklam z wykorzystaniem wariantów alternatywnych

## 1. Kontekst i główna koncepcja projektu
Naszym celem jest stworzenie systemu do klasyfikacji oraz grupowania reklam (w tym wykrywania fake newsów), który opiera się na rozszerzonej bazie danych zawierającej zarówno oryginalne treści, jak i ich zmodyfikowane, alternatywne wersje.

---

## 2. Kluczowe założenia funkcjonalne

### 2.1. Baza danych i generowanie wersji alternatywnych
* W bazie danych przechowywane są oryginalne przykłady fake newsów/reklam oraz wygenerowane na ich podstawie **alternatywne wersje**.
* Wersje alternatywne powstają poprzez modyfikację wybranych atrybutów treści (np. zmiana koloru skóry, występującej osoby, marki samochodu itp.).
* **Dynamiczna konfiguracja zmian:** liczba oraz zakres modyfikowanych cech nie są stałe – powinny być dynamiczne i możliwe do dostrojenia w trakcie fazy testów.

### 2.2. Klasyfikacja podobieństwa i grupowanie nowych reklam
* Podczas klasyfikacji nowej reklamy model porównuje jej podobieństwo ze wszystkimi rekordami w bazie danych – zarówno z oryginałami, jak i z ich wersjami alternatywnymi.
* Na podstawie wyliczonego podobieństwa system tworzy **grupy reklam (klastry)**.
* **Nakładanie się grup:** utworzone grupy reklamowe mogą się ze sobą w pewnym stopniu pokrywać (jedna reklama może pasować do więcej niż jednej grupy).
* **Obsługa nowych przypadków:** jeśli analizowana reklama nie jest wystarczająco podobna do żadnego z istniejących wpisów lub grup, system tworzy na jej podstawie **nową grupę reklamową**.

### 2.3. Istotność cech w procesie grupowania
System musi rozróżniać cechy relewantne od nieistotnych (lub wrażliwych), aby uniknąć błędnego bądź szkodliwego grupowania:
* **Cechy istotne (powinny wpływać na grupowanie):** m.in. reklamowana firma/marka, główny cel reklamy, przekaz itp.
* **Cechy nieistotne (nie powinny determinować grup):** np. cechy demograficzne lub powierzchowne, takie jak kolor skóry (tworzenie grupy reklamowej wyłącznie dla białych osób nie ma sensu merytorycznego).

---

## 3. Zadanie do wykonania
Na podstawie powyższych założeń:
1. **Opracuj kompletny, szczegółowy plan działania (roadmapę) realizacji tego projektu krok po kroku.**
2. **Uwzględnij wszystkie istotne aspekty, na które należy zwrócić uwagę** (m.in. architekturę danych, dobór modeli, metryki podobieństwa, dobór cech, testy, potencjalne ryzyka oraz wyzwania techniczne i etyczne).